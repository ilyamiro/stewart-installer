import os
import re
import sys
import time
import yaml
import shutil
import locale
import signal
import threading
import subprocess
import concurrent.futures
import http.client
from pathlib import Path
from urllib.parse import urlparse
import flet as ft

PROJECT_DIR = Path(__file__).resolve().parent
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


class StewartInstaller:
    def __init__(self):
        self.installing = False
        self.localizer = Localizer(get_system_language())
        self.installation_folder = os.path.expanduser('~')
        self.page = None
        self._init_ui_components()

    def _init_ui_components(self):
        self._create_language_menu()
        self._create_app_bar()
        self._create_progress_bar()
        self._create_overview()
        self._create_image()
        self._create_buttons()

    def _create_language_menu(self):
        self.language_items = []
        for locale in self.localizer.locales.keys():
            self.language_items.append(
                ft.PopupMenuItem(
                    content=ft.Row([
                        ft.Image(
                            src=f"{PROJECT_DIR}/data/assets/languages/{locale}.png",
                            fit=ft.ImageFit.CONTAIN,
                            width=28,
                            height=20
                        ),
                        ft.Text(locale, size=18),
                    ]),
                    on_click=self.change_locale,
                    data=locale
                )
            )

        self.language_change = ft.PopupMenuButton(
            tooltip=self.localizer.translate("choose-lang"),
            icon=ft.Icons.LANGUAGE,
            padding=10,
            items=self.language_items,
            icon_size=32,
            menu_padding=0
        )

    def _create_app_bar(self):
        self.appbar = ft.AppBar(actions=[self.language_change])

    def _create_progress_bar(self):
        self.progress_bar = ft.ProgressBar(
            width=400,
            color=PURPLE,
            bar_height=10,
            value=0,
            visible=False
        )

    def _create_overview(self):
        self.overview = ft.Markdown(scale=1.2)
        self.overview.value = self.localizer.translate("file-pick", directory=self.installation_folder)

    def _create_image(self):
        self.image = ft.Image(
            src=f"{PROJECT_DIR}/data/assets/stewart_logo.png",
            fit=ft.ImageFit.CONTAIN,
            width=450,
            height=450
        )

    def _create_buttons(self):
        self.install_button = ft.TextButton(
            icon=ft.Icons.DOWNLOADING,
            icon_color="white",
            text=self.localizer.translate("install"),
            scale=1.5,
            style=ft.ButtonStyle(
                color="white",
                bgcolor=PURPLE,
                elevation=4,
                icon_size=20
            ),
            on_click=self.install
        )

        self.pick_dir_button = ft.IconButton(
            icon=ft.Icons.FOLDER_ROUNDED,
            icon_size=34,
            icon_color="white",
            on_click=self.file_pick,
            bgcolor=PURPLE
        )

    def change_locale(self, e):
        if self.installing:
            snack_bar = ft.SnackBar(
                content=ft.Text(self.localizer.translate("change-lang"), color="white", size=18),
                behavior=ft.SnackBarBehavior.FLOATING,
                duration=1000,
                width=550,
                bgcolor=PURPLE
            )
            self.page.open(snack_bar)
            return

        lang = e.control.data
        self.localizer.set_language(lang)
        self.overview.value = self.localizer.translate("file-pick", directory=self.installation_folder)
        self.install_button.text = self.localizer.translate("install")
        self.page.update()

    def launch(self, e):
        subprocess.Popen(
            ["bash", "data/scripts/launch.sh", f"{self.installation_folder}/stewart"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def file_pick(self, e):
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

        self.overview.value = self.localizer.translate("file-pick", directory=self.installation_folder)
        self.overview.update()

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

    def info(self, value):
        self.overview.value = value
        self.overview.update()

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

    def internet_connection(self, hosts=None, timeout=3) -> bool:
        if hosts is None:
            hosts = ["https://github.com"]

        with concurrent.futures.ThreadPoolExecutor() as executor:
            futures = [executor.submit(self.check_host, host, timeout) for host in hosts]
            for future in concurrent.futures.as_completed(futures):
                if future.result():
                    return True
        return False

    def install(self, e):
        self.installing = True
        self.image.src = f"{PROJECT_DIR}/data/assets/loading.gif"
        self.image.update()

        self.progress_bar.visible = True
        self.set_progress(0)

        if not self._check_internet_connection():
            return

        self._prepare_installation()

    def _check_internet_connection(self):
        self.info(self.localizer.translate("check-internet"))
        self.set_progress(0.05)

        if not self.internet_connection():
            self.info(self.localizer.translate("no-internet"))
            return False

        self.info(self.localizer.translate("internet-confirm"))
        self.set_progress(0.10)
        return True

    def _prepare_installation(self):
        try:
            path = os.path.join(self.installation_folder, "stewart")

            self.info(self.localizer.translate("prepare-install-dir"))
            self.set_progress(0.15)

            if os.path.exists(path):
                self.info(self.localizer.translate("dir-exists"))
                shutil.rmtree(path)

            os.mkdir(path)
            self.set_progress(0.20)

            self._clone_repository(path)
        except Exception as err:
            self.info(f"❌ Error: {err}")

    def _clone_repository(self, path):
        self.info(self.localizer.translate("cloning-github"))

        process = subprocess.Popen(
            ["git", "clone", "-b", "development", "--progress", GITHUB_URL, path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            bufsize=1
        )

        for line in process.stderr:
            if "Receiving objects" in line:
                try:
                    progress = int(line.split("%")[0].split()[-1])
                    progress_value = 0.20 + (progress * 0.0025)
                    self.set_progress(progress_value, animate=False)
                    self.info(self.localizer.translate("download-repo-percent", progress=progress))
                except (IndexError, ValueError):
                    pass

        process.wait()

        if process.returncode == 0:
            self.info(self.localizer.translate("repo-success"))
            self.set_progress(0.45)
            self.run_installation_script(path)
        else:
            self.info(self.localizer.translate("repo-fail"))

    def run_installation_script(self, path):
        self.info(self.localizer.translate("check-python-install"))
        self.set_progress(0.50)

        process = subprocess.Popen(
            ["bash", "data/scripts/install.sh", path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            bufsize=1
        )

        self._process_installation_output(process)
        self._finalize_installation(process)

    def _process_installation_output(self, process):
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
            self.info(self.localizer.translate("python-installed"))
            current_stage = "packages_install"
            self.set_progress(progress_stages[current_stage])

        elif "Python 3.11 not found" in line:
            self.info(self.localizer.translate("python-not-found"))
            current_stage = "python_install"
            self.set_progress(progress_stages[current_stage])

        elif any(pkg in line for pkg in ["Detected apt", "Detected dnf", "Detected yum", "Detected pacman", "Detected zypper"]):
            pkg_manager = line.split("(")[1].split(")")[0] if "(" in line else "system packages"
            self.info(self.localizer.translate("install-pkg-manager", pkg_manager=pkg_manager))

        elif "Installing additional packages" in line:
            self.info(self.localizer.translate("additional-pkg"))
            current_stage = "packages_install"
            self.set_progress(progress_stages[current_stage])

        elif "python3.11 -m venv venv" in line or "Creating virtual environment" in line:
            self.info(self.localizer.translate("python-venv"))
            current_stage = "venv_setup"
            self.set_progress(progress_stages[current_stage])

        elif "pip install -r requirements.txt" in line or "Installing requirements" in line:
            self.info(self.localizer.translate("requirements"))
            current_stage = "requirements_install"
            self.set_progress(progress_stages[current_stage])

        elif "Successfully installed" in line:
            packages = re.findall(r'Successfully installed (.+)', line)
            if packages:
                package_list = packages[0].replace('-', ' ').split()[:10]
                self.info(self.localizer.install("success-python", pkg_list=', '.join(package_list)))

        elif "Collecting" in line and "pip" not in line.lower():
            package = line.replace("Collecting ", "").split()[0]
            self.info(self.localizer.translate("install-pkg-sep", package=package))

        return current_stage

    def _finalize_installation(self, process):
        process.wait()

        self.install_button.icon = ft.Icons.START
        self.install_button.text = self.localizer.translate("launch")
        self.install_button.on_click = self.launch
        self.install_button.update()

        if process.returncode == 0:
            self.info(self.localizer.translate("install-success"))
            self.set_progress(1.0)
        else:
            self.info(self.localizer.translate("error-install"))

    def build_ui(self, page: ft.Page):
        self.page = page
        self._configure_page()
        self._add_page_content()

    def _configure_page(self):
        self.page.window.height = 680
        self.page.window.width = 1080
        self.page.title = "Stewart"
        self.page.appbar = self.appbar

    def _add_page_content(self):
        self.page.add(
            ft.Column([
                ft.Row([self.image], alignment=ft.MainAxisAlignment.CENTER),
                ft.Row([self.progress_bar], alignment=ft.MainAxisAlignment.CENTER),
                ft.Row([self.overview], alignment=ft.MainAxisAlignment.CENTER),
                ft.Text(),
                ft.Row(
                    [self.install_button, self.pick_dir_button],
                    alignment=ft.MainAxisAlignment.CENTER,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    expand=True,
                    spacing=34
                ),
            ])
        )
        self.page.update()


app = StewartInstaller()
ft.app(app.build_ui)