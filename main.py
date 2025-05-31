import os
import re
import sys
import time
import yaml
import json
import shutil
import locale
import signal
import threading
import subprocess
import concurrent.futures
import http.client
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlparse
import flet as ft

PROJECT_DIR = Path(__file__).resolve().parent
INSTALLED_FILE = f"{PROJECT_DIR}/.updater.json"
GITHUB_URL = "https://github.com/ilyamiro/stewart.git"
PURPLE = "#6736FD"


def get_system_language():
    for var in ['LC_ALL', 'LC_MESSAGES', 'LANG']:
        lang = os.environ.get(var)
        if lang:
            return lang.split('_')[0]

    try:
        lang_locale, _ = locale.getdefaultlocale()
        if lang_locale:
            return lang_locale.split('_')[0]
    except Exception:
        pass

    try:
        result = subprocess.run(['locale'], capture_output=True, text=True)
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if 'LANG=' in line or 'LC_MESSAGES=' in line:
                    parts = line.split('=')
                    if len(parts) == 2 and parts[1]:
                        return parts[1].split('_')[0]
    except Exception:
        pass

    return 'ru'


class Localizer:
    def __init__(self, lang, locales_dir='data/locales'):
        self.locales_dir = locales_dir
        self.lang = lang
        self.locales = {}
        self.load_all_translations()

    def load_all_translations(self):
        if not os.path.isdir(self.locales_dir):
            print(f"Warning: Locales directory '{self.locales_dir}' does not exist.")
            return

        for filename in os.listdir(self.locales_dir):
            if filename.endswith('.yaml'):
                self._load_translation_file(filename)

    def _load_translation_file(self, filename):
        lang_code = os.path.splitext(filename)[0]
        path = os.path.join(self.locales_dir, filename)
        try:
            with open(path, 'r', encoding='utf-8') as file:
                self.locales[lang_code] = yaml.safe_load(file) or {}
        except (FileNotFoundError, yaml.YAMLError) as e:
            print(f"Error loading '{path}': {e}")

    def set_language(self, lang):
        if lang in self.locales:
            self.lang = lang
        else:
            print(f"Warning: Language '{lang}' not loaded. Available: {list(self.locales.keys())}")

    def translate(self, key, **kwargs):
        text = self.locales.get(self.lang, {}).get(key, key)
        try:
            return text.format(**kwargs)
        except KeyError as e:
            print(f"Warning: Missing placeholder {e} in translation for key '{key}'")
            return text


class NetworkManager:
    @staticmethod
    def check_host(host, timeout=3):
        try:
            parsed_url = urlparse(host)
            conn = http.client.HTTPSConnection(parsed_url.netloc, timeout=timeout)
            conn.request("HEAD", parsed_url.path or "/")
            response = conn.getresponse()
            return 200 <= response.status < 400
        except Exception:
            return False

    def internet_connection(self, hosts=None, timeout=3):
        if hosts is None:
            hosts = ["https://github.com"]

        with concurrent.futures.ThreadPoolExecutor() as executor:
            futures = [executor.submit(self.check_host, host, timeout) for host in hosts]
            for future in concurrent.futures.as_completed(futures):
                if future.result():
                    return True
        return False


class GitManager:
    @staticmethod
    def skip_work_tree(path, name):
        dir_skip = path / name
        if dir_skip.exists() and dir_skip.is_dir():
            for file in dir_skip.rglob("*"):
                if file.is_file():
                    rel_path = file.relative_to(path)

                    result = subprocess.run(
                        ["git", "ls-files", "--error-unmatch", str(rel_path)],
                        cwd=path,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL
                    )
                    if result.returncode == 0:
                        subprocess.run(
                            ["git", "update-index", "--skip-worktree", str(rel_path)],
                            cwd=path,
                            check=True
                        )
    @staticmethod
    def clone_repository(repo_url, target_path, branch="development"):
        return subprocess.Popen(
            ["git", "clone", "-b", branch, "--progress", repo_url, target_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            bufsize=1
        )

    @staticmethod
    def pull_updates(path):
        return subprocess.run(
            ["git", "pull"],
            cwd=path,
            capture_output=True,
            text=True,
            check=True
        )


class VersionManager:
    @staticmethod
    def has_relevant_updates(path):
        subprocess.run(["git", "fetch", "--all"], cwd=path, check=True)

        result = subprocess.run(
            ["git", "diff", "--name-only", "origin/development", "development"],
            cwd=path,
            capture_output=True, text=True, check=True
        )

        changed_files = result.stdout.strip().split("\n")
        if changed_files == ['']:
            changed_files = []

        excluded_dirs = ("plugins/core/", "plugins/custom/", "plugins/gpt/", "config/", "docs/")
        relevant_changes = [
            f for f in changed_files if not any(f.startswith(d) for d in excluded_dirs)
        ]

        return bool(relevant_changes)

    @staticmethod
    def get_local_version_info(installed_file):
        if not os.path.exists(installed_file):
            return None

        with open(installed_file, "r", encoding="utf-8") as file:
            data = json.load(file)

        path_to_updater = Path(data["path"]) / ".updater.json"
        if not os.path.exists(path_to_updater):
            return None

        with open(path_to_updater, "r", encoding="utf-8") as file:
            local_data = json.load(file)

        local_version = local_data.get("version")
        repository = local_data.get("repository")

        if not repository or not local_version:
            return None

        return {
            "version": local_version,
            "repository": repository,
            "path": data["path"]
        }

    @staticmethod
    def get_remote_version(repository):
        repo_path = "/".join(repository.split("/")[-2:])
        raw_url = f"https://raw.githubusercontent.com/{repo_path}/development/.updater.json"

        try:
            result = subprocess.run(
                ["curl", "-s", raw_url],
                capture_output=True, text=True, check=True
            )
            remote_json = result.stdout
        except subprocess.CalledProcessError:
            try:
                result = subprocess.run(
                    ["wget", "-qO-", raw_url],
                    capture_output=True, text=True, check=True
                )
                remote_json = result.stdout
            except subprocess.CalledProcessError:
                return None

        remote_data = json.loads(remote_json)
        return remote_data.get("version")

    @staticmethod
    def write_install_info(data):
        with open(INSTALLED_FILE, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False)

    @staticmethod
    def update_version_file(path, version):
        updater_file = f"{path}/.updater.json"
        with open(updater_file, "r", encoding="utf-8") as file:
            data = json.load(file)

        data["version"] = version

        with open(updater_file, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False)


class UIComponents:
    def __init__(self, localizer):
        self.localizer = localizer
        self.language_items = []
        self.language_change = None
        self.app_bar_file_pick = None
        self.app_bar_launch_github = None
        self.appbar = None
        self.progress_bar = None
        self.overview = None
        self.image = None
        self.install_button = None
        self.remove_button = None
        self.update_button = None

    def create_language_menu(self):
        for locale in self.localizer.locales.keys():
            self.language_items.append(
                ft.PopupMenuItem(
                    content=ft.Row([
                        ft.Image(
                            src=f"{PROJECT_DIR}/data/assets/languages/{locale}.png",
                            fit=ft.ImageFit.CONTAIN,
                            width=24,
                            height=16,
                        ),
                        ft.Text(locale, size=20),
                    ]),
                    on_click=None,
                    data=locale,
                    padding=4
                )
            )

        self.language_change = ft.PopupMenuButton(
            tooltip=self.localizer.translate("choose-lang"),
            icon=ft.Icons.LANGUAGE,
            items=self.language_items,
            menu_padding=0,
            style=ft.ButtonStyle(
                padding=0,
                color="white",
                icon_size=30,
            ),
        )

    def create_app_bar_components(self, installation_folder):
        self.app_bar_file_pick = ft.Text(
            value=installation_folder,
            style=ft.TextStyle(
                size=20,
                color="white",
            ),
        )

        self.app_bar_launch_github = ft.TextButton(
            icon=ft.Icons.LINK,
            text="GitHub",
            on_click=None,
            style=ft.ButtonStyle(
                padding=0,
                color="white",
                icon_size=28,
                text_style=ft.TextStyle(
                    size=18
                )
            ),
            tooltip=GITHUB_URL
        )

        self.appbar = ft.AppBar(
            leading=self.app_bar_launch_github,
            leading_width=120,
            title=self.app_bar_file_pick,
            center_title=True,
            actions=[
                self.language_change
            ],
        )

    def create_progress_bar(self):
        self.progress_bar = ft.ProgressBar(
            width=400,
            color=PURPLE,
            bar_height=20,
            value=0,
            visible=False
        )

    def create_overview(self):
        self.overview = ft.Markdown(scale=1.4)

    def create_image(self):
        self.image = ft.Image(
            src=f"{PROJECT_DIR}/data/assets/stewart_logo.png",
            fit=ft.ImageFit.CONTAIN,
            width=450,
            height=450
        )

    def create_buttons(self):
        self.install_button = ft.TextButton(
            icon=ft.Icons.DOWNLOADING,
            icon_color="white",
            text=self.localizer.translate("install"),
            scale=1.5,
            style=ft.ButtonStyle(
                padding=10,
                color="white",
                bgcolor=PURPLE,
                elevation=4,
                icon_size=25
            ),
            on_click=None
        )

        self.remove_button = ft.TextButton(
            icon=ft.Icons.DELETE,
            icon_color="white",
            disabled=True,
            opacity=0.4,
            text=self.localizer.translate("delete"),
            scale=1.5,
            style=ft.ButtonStyle(
                padding=10,
                color="white",
                bgcolor=PURPLE,
                elevation=4,
                icon_size=25
            ),
            on_click=None
        )

        self.update_button = ft.TextButton(
            icon=ft.Icons.UPDATE,
            opacity=0.4,
            icon_color="white",
            disabled=True,
            text=self.localizer.translate("update"),
            scale=1.5,
            style=ft.ButtonStyle(
                padding=10,
                color="white",
                bgcolor=PURPLE,
                elevation=4,
                icon_size=25,
            ),
            on_click=None,
        )


class InstallationProgress:
    def __init__(self, progress_bar, overview):
        self.progress_bar = progress_bar
        self.overview = overview

    def set_progress(self, value, animate=True):
        if animate and self.progress_bar.value < value:
            def smooth_progress():
                start_value = self.progress_bar.value
                steps = 30
                increment = (value - start_value) / steps

                for i in range(steps):
                    self.progress_bar.value = start_value + (increment * (i + 1))
                    time.sleep(0.03)
                    self.progress_bar.update()

                self.progress_bar.value = value
                self.progress_bar.update()

            thread = threading.Thread(target=smooth_progress)
            thread.start()
        else:
            self.progress_bar.value = value
            self.progress_bar.update()

    def update_info(self, message):
        self.overview.value = message
        self.overview.update()


class InstallationHandler:
    def __init__(self, progress, localizer):
        self.progress = progress
        self.localizer = localizer

    def process_installation_output(self, process):
        current_stage = "python_check"
        progress_stages = {
            "python_check": 0.50,
            "python_install": 0.60,
            "packages_install": 0.75,
            "venv_setup": 0.85,
            "requirements_install": 0.95,
            "complete": 1.0
        }

        for line in process.stdout:
            line = line.strip()
            current_stage = self._handle_installation_line(line, current_stage, progress_stages)

    def _handle_installation_line(self, line, current_stage, progress_stages):
        if "Python 3.11 is already installed" in line:
            self.progress.update_info(self.localizer.translate("python-installed"))
            current_stage = "packages_install"
            self.progress.set_progress(progress_stages[current_stage])

        elif "Python 3.11 not found" in line:
            self.progress.update_info(self.localizer.translate("python-not-found"))
            current_stage = "python_install"
            self.progress.set_progress(progress_stages[current_stage])

        elif any(pkg in line for pkg in
                 ["Detected apt", "Detected dnf", "Detected yum", "Detected pacman", "Detected zypper"]):
            pkg_manager = line.split("(")[1].split(")")[0] if "(" in line else "system packages"
            self.progress.update_info(self.localizer.translate("install-pkg-manager", pkg_manager=pkg_manager))

        elif "Installing additional packages" in line:
            self.progress.update_info(self.localizer.translate("additional-pkg"))
            current_stage = "packages_install"
            self.progress.set_progress(progress_stages[current_stage])

        elif "python3.11 -m venv venv" in line or "Creating virtual environment" in line:
            self.progress.update_info(self.localizer.translate("python-venv"))
            current_stage = "venv_setup"
            self.progress.set_progress(progress_stages[current_stage])

        elif "pip install -r requirements.txt" in line or "Installing requirements" in line:
            self.progress.update_info(self.localizer.translate("requirements"))
            current_stage = "requirements_install"
            self.progress.set_progress(progress_stages[current_stage])

        elif "Successfully installed" in line:
            packages = re.findall(r'Successfully installed (.+)', line)
            if packages:
                package_list = packages[0].replace('-', ' ').split()[:10]
                self.progress.update_info(self.localizer.translate("success-python", pkg_list=', '.join(package_list)))

        elif "Collecting" in line and "pip" not in line.lower():
            package = line.replace("Collecting ", "").split()[0]
            self.progress.update_info(self.localizer.translate("install-pkg-sep", package=package))

        elif "torch" in line:
            self.progress.update_info(self.localizer.translate("install-torch"))

        return current_stage


class StewartInstaller:
    def __init__(self):
        self.installing = False
        self.update_exists = False
        self.no_detect = True

        self.local_version = "___"
        self.remote_version = "___"

        self.localizer = Localizer(get_system_language())
        self.installation_folder = os.path.expanduser('~')
        self.existing_installation_folder = None
        self.page = None

        self.network_manager = NetworkManager()
        self.git_manager = GitManager()
        self.version_manager = VersionManager()
        self.ui_components = UIComponents(self.localizer)

        self._init_ui_components()

    def _init_ui_components(self):
        self.ui_components.create_language_menu()
        self.ui_components.create_app_bar_components(self.installation_folder)
        self.ui_components.create_progress_bar()
        self.ui_components.create_overview()
        self.ui_components.create_image()
        self.ui_components.create_buttons()

        self._bind_event_handlers()

    def _bind_event_handlers(self):
        for item in self.ui_components.language_items:
            item.on_click = self.change_locale

        self.ui_components.app_bar_launch_github.on_click = self.launch_github
        self.ui_components.install_button.on_click = self.install
        self.ui_components.update_button.on_click = self.update
        self.ui_components.remove_button.on_click = self.uninstall

    def _find_existing_installation(self):
        version_info = self.version_manager.get_local_version_info(INSTALLED_FILE)

        self.ui_components.progress_bar.value = 0
        self.ui_components.progress_bar.visible = False
        self.ui_components.progress_bar.update()

        if not version_info:
            self._handle_no_installation()
            return

        remote_version = self.version_manager.get_remote_version(version_info["repository"])
        if not remote_version:
            return

        self.local_version = version_info["version"]
        self.remote_version = remote_version
        self.existing_installation_folder = version_info["path"]

        if remote_version != version_info["version"] or self.version_manager.has_relevant_updates(version_info["path"]):
            self._handle_update_available(version_info, remote_version)
        else:
            self._handle_current_installation(version_info)

    def _handle_no_installation(self):
        self.no_detect = True
        self.ui_components.app_bar_file_pick.value = self.installation_folder

        self.ui_components.update_button.disabled = True
        self.ui_components.update_button.opacity = 0.4
        self.ui_components.update_button.text = self.localizer.translate("update")
        self.ui_components.update_button.icon = ft.Icons.UPDATE
        self.ui_components.update_button.on_click = self.update

        self.ui_components.remove_button.disabled = True
        self.ui_components.remove_button.opacity = 0.4
        self.ui_components.remove_button.update()

        self._update_info(self.localizer.translate("found-no-install"))
        self.page.update()

    def _handle_update_available(self, version_info, remote_version):
        self.update_exists = True
        self.no_detect = False

        self.ui_components.update_button.disabled = False
        self.ui_components.update_button.opacity = 1.0
        self.ui_components.update_button.on_click = self.update
        self.ui_components.update_button.data = (remote_version, version_info["path"])
        self.ui_components.update_button.update()

        self.ui_components.remove_button.disabled = False
        self.ui_components.remove_button.opacity = 1.0
        self.ui_components.remove_button.update()

        if version_info != remote_version:
            self.ui_components.overview.value = self.localizer.translate(
                "update-from",
                local_version=version_info["version"],
                remote_version=remote_version
            )
        else:
            self.ui_components.overview.value = self.localizer.translate(
                "bugfix",
                local_version=version_info["version"],
            )

        self.ui_components.overview.update()

        self.ui_components.app_bar_file_pick.value = version_info["path"]
        self.ui_components.app_bar_file_pick.update()

    def _handle_current_installation(self, version_info):
        self.no_detect = False

        self.ui_components.update_button.disabled = False
        self.ui_components.update_button.opacity = 1.0
        self.ui_components.update_button.text = self.localizer.translate("launch")
        self.ui_components.update_button.icon = ft.Icons.OPEN_IN_BROWSER
        self.ui_components.update_button.on_click = self.launch

        self.ui_components.update_button.update()

        self.ui_components.app_bar_file_pick.value = version_info["path"]
        self.ui_components.app_bar_file_pick.update()

        self.ui_components.remove_button.disabled = False
        self.ui_components.remove_button.opacity = 1.0
        self.ui_components.remove_button.update()

        self.ui_components.overview.value = self.localizer.translate(
            "found-install",
            local_version=version_info["version"]
        )
        self.ui_components.overview.update()

    def update(self, e):
        self.ui_components.remove_button.disabled = True
        self.ui_components.remove_button.opacity = 0.4
        self.ui_components.remove_button.update()

        self.ui_components.image.src = f"{PROJECT_DIR}/data/assets/loading.gif"
        self.ui_components.image.update()

        install_path = Path(e.control.data[1])
        git_dir = install_path / ".git"

        if not git_dir.exists():
            self._update_info(self.localizer.translate("no-git-path", install_path=install_path))
            return

        try:
            self.git_manager.skip_work_tree(install_path, "config")
            self.git_manager.skip_work_tree(install_path, "plugins")

            result = self.git_manager.pull_updates(install_path)
            self.version_manager.update_version_file(str(install_path), e.control.data[0])

            self._update_info(self.localizer.translate("update-successful", result=result.stdout))
            self.ui_components.image.src = f"{PROJECT_DIR}/data/assets/stewart_logo.png"
            self.ui_components.image.update()

            self.ui_components.remove_button.disabled = False
            self.ui_components.remove_button.opacity = 1.0
            self.ui_components.remove_button.update()

        except subprocess.CalledProcessError as err:
            self._update_info(self.localizer.translate("update-fail", error=err.stderr))


    def change_locale(self, e):
        if self.installing:
            snack_bar = ft.SnackBar(
                content=ft.Text(self.localizer.translate("change-lang"), color="white", size=18),
                behavior=ft.SnackBarBehavior.FIXED,
                duration=2000,
                width=550,
            )
            self.page.open(snack_bar)
            return

        lang = e.control.data
        self.localizer.set_language(lang)
        self._update_ui_text()

    def _update_ui_text(self):
        self.ui_components.install_button.text = self.localizer.translate("install")
        self.ui_components.remove_button.text = self.localizer.translate("delete")

        if self.no_detect:
            self.ui_components.update_button.text = self.localizer.translate("update")
            self.ui_components.overview.value = self.localizer.translate("found-no-install")
        else:
            if self.update_exists:
                self.ui_components.update_button.text = self.localizer.translate("update")
                self.ui_components.overview.value = self.localizer.translate(
                    "update-from",
                    local_version=self.local_version,
                    remote_version=self.remote_version
                )
            else:
                self.ui_components.update_button.text = self.localizer.translate("launch")
                self.ui_components.overview.value = self.localizer.translate(
                    "found-install",
                    local_version=self.local_version
                )

        self.page.update()

    def launch_github(self, e):
        self.page.launch_url(GITHUB_URL)

    @staticmethod
    def launch(e):
        subprocess.Popen(
            ["bash", f"{PROJECT_DIR}/data/scripts/launch.sh"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def file_pick(self):
        command = [
            'zenity',
            '--file-selection',
            f'--title={self.localizer.translate("choose-dir")}',
            '--directory'
        ]
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        directory = result.stdout.decode('utf-8').strip()

        if directory:
            self.installation_folder = directory

    def _update_info(self, message):
        self.ui_components.overview.value = message
        self.ui_components.overview.update()

    def install(self, e):
        self.file_pick()
        self.start_installation()

    def uninstall(self, e):
        self.ui_components.image.src = f"{PROJECT_DIR}/data/assets/loading.gif"
        self.ui_components.image.update()

        self.ui_components.progress_bar.visible = True
        progress = InstallationProgress(
            self.ui_components.progress_bar,
            self.ui_components.overview
        )
        progress.set_progress(0)

        if self.existing_installation_folder and os.path.exists(self.existing_installation_folder):
            progress.set_progress(0.85)
            self._update_info(self.localizer.translate("remove-folder"))
            shutil.rmtree(self.existing_installation_folder)
            time.sleep(1)

        path_to_desktop = f'{os.path.expanduser("~")}/.local/share/applications/stewart.desktop'
        if os.path.exists(path_to_desktop) and (os.path.isfile(path_to_desktop) or os.path.islink(path_to_desktop)):
            progress.set_progress(0.925)
            time.sleep(0.5)
            self._update_info(self.localizer.translate("remove-desktop"))
            os.remove(path_to_desktop)

        path_to_updater = f"{PROJECT_DIR}/.updater.json"
        if os.path.exists(path_to_updater):
            progress.set_progress(1)
            time.sleep(0.5)
            os.remove(path_to_updater)

        self._update_info(self.localizer.translate("remove-success"))
        self.ui_components.image.src = f"{PROJECT_DIR}/data/assets/stewart_logo.png"
        self.ui_components.image.update()

        self._find_existing_installation()

    def start_installation(self):
        self.ui_components.update_button.disabled = True
        self.ui_components.update_button.opacity = 0.4
        self.ui_components.update_button.icon = ft.Icons.UPDATE
        self.ui_components.update_button.text = self.localizer.translate("update")
        self.ui_components.update_button.style.text_style = None
        self.ui_components.update_button.update()

        self.installing = True
        self.ui_components.image.src = f"{PROJECT_DIR}/data/assets/loading.gif"
        self.ui_components.image.update()

        self.ui_components.progress_bar.visible = True

        progress = InstallationProgress(
            self.ui_components.progress_bar,
            self.ui_components.overview
        )
        progress.set_progress(0)

        if not self._check_internet_connection(progress):
            return

        self._prepare_installation(progress)

    def _check_internet_connection(self, progress):
        progress.update_info(self.localizer.translate("check-internet"))
        progress.set_progress(0.05)

        if not self.network_manager.internet_connection():
            progress.update_info(self.localizer.translate("no-internet"))
            return False

        progress.update_info(self.localizer.translate("internet-confirm"))
        progress.set_progress(0.10)
        return True

    def _prepare_installation(self, progress):
        try:
            path = os.path.join(self.installation_folder, "stewart")

            progress.update_info(self.localizer.translate("prepare-install-dir"))
            progress.set_progress(0.15)

            if os.path.exists(path):
                progress.update_info(self.localizer.translate("dir-exists"))
                shutil.rmtree(path)

            os.mkdir(path)
            progress.set_progress(0.20)

            self._clone_repository(path, progress)
        except Exception as err:
            progress.update_info(f"❌ Error: {err}")

    def _clone_repository(self, path, progress):
        progress.update_info(self.localizer.translate("cloning-github"))

        process = self.git_manager.clone_repository(GITHUB_URL, path)

        for line in process.stderr:
            if "Receiving objects" in line:
                try:
                    progress_percent = int(line.split("%")[0].split()[-1])
                    progress_value = 0.20 + (progress_percent * 0.0025)
                    progress.set_progress(progress_value, animate=False)
                    progress.update_info(self.localizer.translate("download-repo-percent", progress=progress_percent))
                except (IndexError, ValueError):
                    pass

        process.wait()

        if process.returncode == 0:
            progress.update_info(self.localizer.translate("repo-success"))
            progress.set_progress(0.45)
            self._run_installation_script(path, progress)
        else:
            progress.update_info(self.localizer.translate("repo-fail"))

    def _run_installation_script(self, path, progress):
        progress.update_info(self.localizer.translate("check-python-install"))
        progress.set_progress(0.50)

        process = subprocess.Popen(
            ["bash", "data/scripts/install.sh", path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            bufsize=1
        )

        handler = InstallationHandler(progress, self.localizer)
        handler.process_installation_output(process)
        self._finalize_installation(process, progress)

    def _finalize_installation(self, process, progress):
        process.wait()

        data = {
            "path": f"{self.installation_folder}/stewart",
            "install_date": datetime.now(timezone.utc).isoformat()
        }

        self.version_manager.write_install_info(data)

        self.installing = False
        self.no_detect = False

        self.ui_components.image.src = f"{PROJECT_DIR}/data/assets/stewart_logo.png"
        self.ui_components.image.update()

        if process.returncode == 0:
            progress.update_info(self.localizer.translate("install-success"))
            progress.set_progress(1.0)
        else:
            progress.update_info(self.localizer.translate("error-install"))

        self._find_existing_installation()
        self._create_desktop_stewart_shortcut()

    @staticmethod
    def _create_desktop_shortcut():
        subprocess.run(
            ["bash", f"{PROJECT_DIR}/data/scripts/create_entry.sh"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def _create_desktop_stewart_shortcut(self):
        subprocess.run(
            ["bash", f"{PROJECT_DIR}/data/scripts/create_entry_stewart.sh", self.existing_installation_folder],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def build_ui(self, page: ft.Page):
        self.page = page
        self._configure_page()
        self._add_page_content()
        self._create_desktop_shortcut()
        self._find_existing_installation()

    def _configure_page(self):
        self.page.window.height = 680
        self.page.window.width = 1080
        self.page.theme_mode = ft.ThemeMode.DARK
        self.page.title = "Stewart"
        self.page.appbar = self.ui_components.appbar

    def _add_page_content(self):
        self.page.add(
            ft.Column([
                ft.Row([self.ui_components.image], alignment=ft.MainAxisAlignment.CENTER),
                ft.Row([self.ui_components.progress_bar], alignment=ft.MainAxisAlignment.CENTER),
                ft.Row([self.ui_components.overview], alignment=ft.MainAxisAlignment.CENTER),
                ft.Text(),
                ft.Row(
                    [self.ui_components.update_button, self.ui_components.install_button, self.ui_components.remove_button],
                    alignment=ft.MainAxisAlignment.CENTER,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=65,
                    expand=True,
                ),
            ])
        )
        self.page.update()


app = StewartInstaller()
ft.app(app.build_ui)
