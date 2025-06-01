import os
import re
import sys
import time
import yaml
import json
import shutil
import platform
import psutil
import locale
import signal
import threading
import subprocess
import concurrent.futures
import tempfile
import http.client
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlparse
import flet as ft

PROJECT_DIR = Path(__file__).resolve().parent
INSTALLED_FILE = f"{PROJECT_DIR}/.updater.json"
GITHUB_URL = "https://github.com/ilyamiro/stewart.git"
PURPLE = "#6736FD"
RED = "#E5484D"


class SystemInfo:
    @staticmethod
    def get_cpu_name():
        cpu = platform.processor()
        if cpu and cpu != 'unknown':
            return cpu.strip()

        uname = platform.uname()
        if uname.processor and uname.processor != 'unknown':
            return uname.processor.strip()

        if sys.platform.startswith('linux'):
            try:
                with open("/proc/cpuinfo", "r") as f:
                    for line in f:
                        if "model name" in line:
                            return line.strip().split(":")[1].strip()
            except FileNotFoundError:
                pass

        if sys.platform == "darwin":
            try:
                import subprocess
                return subprocess.check_output(
                    ["sysctl", "-n", "machdep.cpu.brand_string"]
                ).strip().decode()
            except Exception:
                pass

        if sys.platform == "win32":
            return os.environ.get("PROCESSOR_IDENTIFIER", "").strip()

        return "Unknown CPU"

    @staticmethod
    def get_gpu_info():
        """Get GPU information using built-in system commands (no external dependencies)"""
        gpu_info = {
            "gpu_name": "Unknown GPU",
            "gpu_memory": "Unknown",
            "gpu_driver": "Unknown",
            "gpu_temp": "Unknown"
        }

        try:
            import subprocess

            if sys.platform == "win32":
                # Use Windows built-in wmic command
                try:
                    # Get GPU name
                    result = subprocess.check_output([
                        "wmic", "path", "win32_VideoController", "get", "name", "/format:list"
                    ], stderr=subprocess.DEVNULL, text=True).strip()

                    for line in result.split('\n'):
                        if line.startswith('Name=') and line != 'Name=':
                            gpu_info["gpu_name"] = line.split('=', 1)[1].strip()
                            break

                    # Get GPU memory
                    result = subprocess.check_output([
                        "wmic", "path", "win32_VideoController", "get", "AdapterRAM", "/format:list"
                    ], stderr=subprocess.DEVNULL, text=True).strip()

                    for line in result.split('\n'):
                        if line.startswith('AdapterRAM=') and line != 'AdapterRAM=':
                            try:
                                ram_bytes = int(line.split('=', 1)[1].strip())
                                gpu_info["gpu_memory"] = f"{ram_bytes // (1024 ** 2)} MB"
                            except (ValueError, ZeroDivisionError):
                                pass
                            break

                    # Get driver version
                    result = subprocess.check_output([
                        "wmic", "path", "win32_VideoController", "get", "DriverVersion", "/format:list"
                    ], stderr=subprocess.DEVNULL, text=True).strip()

                    for line in result.split('\n'):
                        if line.startswith('DriverVersion=') and line != 'DriverVersion=':
                            gpu_info["gpu_driver"] = line.split('=', 1)[1].strip()
                            break

                except (subprocess.CalledProcessError, FileNotFoundError):
                    pass

            elif sys.platform.startswith('linux'):
                # Try lspci first for basic GPU info (works for all GPU vendors)
                try:
                    result = subprocess.check_output([
                        "lspci", "-mm"
                    ], stderr=subprocess.DEVNULL, text=True)

                    for line in result.split('\n'):
                        if 'VGA compatible controller' in line or 'Display controller' in line or '3D controller' in line:
                            # Parse lspci -mm output format
                            parts = line.split('"')
                            if len(parts) >= 6:
                                gpu_info["gpu_name"] = f"{parts[3]} {parts[5]}"
                            break
                except (subprocess.CalledProcessError, FileNotFoundError):
                    pass

                # Try nvidia-smi for NVIDIA-specific info (temperature, memory, driver)
                if "NVIDIA" in gpu_info.get("gpu_name", "").upper() or gpu_info["gpu_name"] == "Unknown GPU":
                    try:
                        result = subprocess.check_output([
                            "nvidia-smi", "--query-gpu=name,memory.total,driver_version,temperature.gpu",
                            "--format=csv,noheader,nounits"
                        ], stderr=subprocess.DEVNULL, text=True).strip()

                        if result and not result.startswith("NVIDIA-SMI has failed"):
                            parts = [p.strip() for p in result.split(',')]
                            if len(parts) >= 4:
                                gpu_info["gpu_name"] = parts[0]
                                gpu_info["gpu_memory"] = f"{parts[1]} MB"
                                gpu_info["gpu_driver"] = parts[2]
                                if parts[3] and parts[3] != "[Not Supported]":
                                    gpu_info["gpu_temp"] = f"{parts[3]}°C"
                    except (subprocess.CalledProcessError, FileNotFoundError):
                        pass

                # Try AMD-specific commands
                if "AMD" in gpu_info.get("gpu_name", "").upper() or "ATI" in gpu_info.get("gpu_name", "").upper():
                    try:
                        # Try to get AMD GPU info from sysfs
                        import glob
                        amd_cards = glob.glob('/sys/class/drm/card*/device/vendor')
                        for card_path in amd_cards:
                            try:
                                with open(card_path, 'r') as f:
                                    vendor = f.read().strip()
                                if vendor == '0x1002':  # AMD vendor ID
                                    # Try to get memory info from sysfs
                                    mem_path = card_path.replace('/vendor', '/mem_info_vram_total')
                                    try:
                                        with open(mem_path, 'r') as f:
                                            mem_bytes = int(f.read().strip())
                                            gpu_info["gpu_memory"] = f"{mem_bytes // (1024 ** 2)} MB"
                                    except (FileNotFoundError, ValueError):
                                        pass
                                    break
                            except (FileNotFoundError, ValueError):
                                continue
                    except ImportError:
                        pass

            elif sys.platform == "darwin":
                try:
                    # Use system_profiler for macOS
                    result = subprocess.check_output([
                        "system_profiler", "SPDisplaysDataType"
                    ], stderr=subprocess.DEVNULL, text=True)

                    # Parse system_profiler output
                    lines = result.split('\n')
                    for i, line in enumerate(lines):
                        if 'Chipset Model:' in line:
                            gpu_info["gpu_name"] = line.split(':', 1)[1].strip()
                        elif 'VRAM (Total):' in line or 'VRAM (Dynamic, Max):' in line:
                            gpu_info["gpu_memory"] = line.split(':', 1)[1].strip()

                except (subprocess.CalledProcessError, FileNotFoundError):
                    pass

        except Exception:
            pass

        return gpu_info

    def get_system_info(self):
        try:
            # Get system information
            system_info = {
                "os": f"{platform.system()} {platform.release()}",
                "architecture": platform.machine(),
                "processor": self.get_cpu_name(),
                "python_version": platform.python_version(),
                "hostname": platform.node(),
            }

            # Get memory information
            memory = psutil.virtual_memory()
            system_info["ram_total"] = f"{memory.total // (1024 ** 3)} GB"
            system_info["ram_available"] = f"{memory.available // (1024 ** 3)} GB"
            system_info["ram_percent"] = f"{memory.percent}%"

            # Get disk information
            disk = psutil.disk_usage('/')
            system_info["disk_total"] = f"{disk.total // (1024 ** 3)} GB"
            system_info["disk_free"] = f"{disk.free // (1024 ** 3)} GB"
            system_info["disk_percent"] = f"{(disk.used / disk.total * 100):.1f}%"

            # Get CPU information
            system_info["cpu_cores"] = psutil.cpu_count(logical=False)
            system_info["cpu_threads"] = psutil.cpu_count(logical=True)
            system_info["cpu_freq"] = f"{psutil.cpu_freq().max:.0f} MHz" if psutil.cpu_freq() else "Unknown"

            # Get GPU information
            gpu_info = self.get_gpu_info()
            system_info.update(gpu_info)

            return system_info
        except Exception as e:
            return {"error": str(e)}


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
    excluded_dirs = ("plugins/core/", "plugins/custom/", "plugins/gpt/", "config/", "docs/")

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
    def backup_excluded_dirs(path, excluded_dirs):
        backup = tempfile.TemporaryDirectory()
        for d in excluded_dirs:
            src = path / d
            dst = Path(backup.name) / d
            if src.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(src, dst, dirs_exist_ok=True)
        return backup

    @staticmethod
    def restore_excluded_dirs(path, backup, excluded_dirs):
        for d in excluded_dirs:
            src = Path(backup.name) / d
            dst = path / d
            if src.exists():
                shutil.copytree(src, dst, dirs_exist_ok=True)

    @staticmethod
    def pull_updates(path, excluded_dirs):
        backup = GitManager.backup_excluded_dirs(path, excluded_dirs)
        try:
            result = subprocess.run(
                ["git", "pull"],
                cwd=path,
                capture_output=True,
                text=True,
                check=True
            )
            GitManager.restore_excluded_dirs(path, backup, excluded_dirs)
            return result
        finally:
            backup.cleanup()


class VersionManager:
    @staticmethod
    def has_relevant_updates(path, excluded_dirs):
        subprocess.run(["git", "fetch", "--all"], cwd=path, check=True)

        result = subprocess.run(
            ["git", "diff", "--name-only", "origin/development", "development"],
            cwd=path,
            capture_output=True, text=True, check=True
        )

        changed_files = result.stdout.strip().split("\n")
        if changed_files == ['']:
            changed_files = []

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
        self.info_dialog = None
        self.appbar = None
        self.progress_bar = None
        self.overview = None
        self.image = None
        self.remove_dialog = None
        self.install_button = None
        self.remove_button = None
        self.update_button = None
        self.remove_yes_button = None
        self.remove_no_button = None

    @staticmethod
    def create_info_card(title, items, icon_name):
        card_items = []
        for label, value in items:
            card_items.append(
                ft.Row([
                    ft.Text(
                        f"{label}:",
                        size=15,
                        color=ft.Colors.with_opacity(0.7, "white"),
                        weight=ft.FontWeight.W_500,
                        width=160
                    ),
                    ft.Text(
                        str(value),
                        size=15,
                        color="white",
                        weight=ft.FontWeight.W_400,
                        selectable=True
                    )
                ], spacing=8)
            )

        return ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Icon(icon_name, color=PURPLE, size=24),
                    ft.Text(
                        title,
                        size=16,
                        color="white",
                        weight=ft.FontWeight.W_600
                    )
                ], spacing=12, alignment=ft.MainAxisAlignment.START),
                ft.Container(height=8),
                ft.Column(card_items, spacing=6)
            ], spacing=0),
            padding=ft.padding.all(16),
            margin=ft.margin.symmetric(vertical=4),
            bgcolor=ft.Colors.with_opacity(0.05, "white"),
            border_radius=12,
            border=ft.border.all(1, ft.Colors.with_opacity(0.1, "white"))
        )

    def copy_system_info(self, e):
        try:
            info_collector = SystemInfo()
            system_info = info_collector.get_system_info()

            info_text = f"=== {self.localizer.translate('system-info-header')} ===\n\n"
            info_text += f"{self.localizer.translate('stewart-info-section')}:\n"
            info_text += f"{self.localizer.translate('local-version')}: {getattr(self, 'local_version', self.localizer.translate('not-installed'))}\n"
            info_text += f"{self.localizer.translate('remote-version')}: {getattr(self, 'remote_version', self.localizer.translate('unknown'))}\n"
            info_text += f"{self.localizer.translate('install-path')}: {getattr(self, 'existing_installation_folder', self.localizer.translate('not-installed'))}\n"
            info_text += f"{self.localizer.translate('repository')}: {GITHUB_URL}\n"
            info_text += f"{self.localizer.translate('language')}: {self.localizer.lang.upper()}\n\n"

            if "error" not in system_info:
                info_text += f"{self.localizer.translate('system-info-section')}:\n"
                info_text += f"{self.localizer.translate('os')}: {system_info.get('os', self.localizer.translate('unknown'))}\n"
                info_text += f"{self.localizer.translate('architecture')}: {system_info.get('architecture', self.localizer.translate('unknown'))}\n"
                info_text += f"{self.localizer.translate('hostname')}: {system_info.get('hostname', self.localizer.translate('unknown'))}\n"
                info_text += f"{self.localizer.translate('python')}: {system_info.get('python_version', self.localizer.translate('unknown'))}\n\n"

                info_text += f"{self.localizer.translate('hardware-info-section')}:\n"
                info_text += f"{self.localizer.translate('processor')}: {system_info.get('processor', self.localizer.translate('unknown'))}\n"
                info_text += f"{self.localizer.translate('cpu-cores')}: {system_info.get('cpu_cores', self.localizer.translate('unknown'))}\n"
                info_text += f"{self.localizer.translate('cpu-threads')}: {system_info.get('cpu_threads', self.localizer.translate('unknown'))}\n"
                info_text += f"{self.localizer.translate('cpu-frequency')}: {system_info.get('cpu_freq', self.localizer.translate('unknown'))}\n\n"

                info_text += f"{self.localizer.translate('memory-storage-section')}:\n"
                info_text += f"{self.localizer.translate('total-ram')}: {system_info.get('ram_total', self.localizer.translate('unknown'))}\n"
                info_text += f"{self.localizer.translate('available-ram')}: {system_info.get('ram_available', self.localizer.translate('unknown'))}\n"
                info_text += f"{self.localizer.translate('ram-usage')}: {system_info.get('ram_percent', self.localizer.translate('unknown'))}\n"
                info_text += f"{self.localizer.translate('total-disk')}: {system_info.get('disk_total', self.localizer.translate('unknown'))}\n"
                info_text += f"{self.localizer.translate('free-disk')}: {system_info.get('disk_free', self.localizer.translate('unknown'))}\n"
                info_text += f"{self.localizer.translate('disk-usage')}: {system_info.get('disk_percent', self.localizer.translate('unknown'))}\n"
            else:
                info_text += f"{self.localizer.translate('system-info-error')}: {system_info['error']}\n"

            # Copy to clipboard using the page's set_clipboard method
            self.page.set_clipboard(info_text)

            snack_bar = ft.SnackBar(
                content=ft.Text(self.localizer.translate("info-copy-success"), color="white", size=16),
                behavior=ft.SnackBarBehavior.FIXED,
                duration=2000,
                bgcolor=PURPLE,
                width=400,
            )
            self.page.open(snack_bar)

        except Exception as error:
            snack_bar = ft.SnackBar(
                content=ft.Text(self.localizer.translate("info-copy-fail", error=str(error)), color="white", size=16),
                behavior=ft.SnackBarBehavior.FIXED,
                duration=3000,
                bgcolor=RED,
                width=400,
            )
            self.page.open(snack_bar)

    def create_info_dialog(self):
        info_collector = SystemInfo()
        system_info = info_collector.get_system_info()

        stewart_items = [
            (self.localizer.translate("version"),
             f"{getattr(self, 'local_version', self.localizer.translate('not-installed'))}"),
            (self.localizer.translate("remote"), getattr(self, 'remote_version', self.localizer.translate('unknown'))),
            (self.localizer.translate("install-path"),
             getattr(self, 'existing_installation_folder', self.localizer.translate('not-installed'))),
            (self.localizer.translate("repository"), GITHUB_URL),
            (self.localizer.translate("language"), self.localizer.lang.upper())
        ]

        stewart_card = self.create_info_card(
            self.localizer.translate("stewart-information"),
            stewart_items,
            ft.Icons.ROCKET_LAUNCH
        )

        if "error" not in system_info:
            system_items = [
                (self.localizer.translate("operating-system"),
                 system_info.get("os", self.localizer.translate("unknown"))),
                (self.localizer.translate("architecture"),
                 system_info.get("architecture", self.localizer.translate("unknown"))),
                (self.localizer.translate("hostname"),
                 system_info.get("hostname", self.localizer.translate("unknown"))),
                (self.localizer.translate("python-version"),
                 system_info.get("python_version", self.localizer.translate("unknown")))
            ]
        else:
            system_items = [(self.localizer.translate("error"), system_info["error"])]

        system_card = self.create_info_card(
            self.localizer.translate("system-information"),
            system_items,
            ft.Icons.COMPUTER
        )

        if "error" not in system_info:
            processor_text = system_info.get("processor", self.localizer.translate("unknown"))
            if len(processor_text) > 50:
                processor_text = processor_text[:50] + "..."

            gpu_name = system_info.get("gpu_name", self.localizer.translate("unknown"))
            if len(gpu_name) > 50:
                gpu_name = gpu_name[:50] + "..."

            hardware_items = [
                (self.localizer.translate("processor"), processor_text),
                (self.localizer.translate("cpu-cores"),
                 f"{system_info.get('cpu_cores', self.localizer.translate('unknown'))} {self.localizer.translate('cores')}"),
                (self.localizer.translate("cpu-threads"),
                 f"{system_info.get('cpu_threads', self.localizer.translate('unknown'))} {self.localizer.translate('threads')}"),
                (self.localizer.translate("cpu-frequency"),
                 system_info.get("cpu_freq", self.localizer.translate("unknown"))),

                (self.localizer.translate("gpu-name"), gpu_name),
                (self.localizer.translate("gpu-memory"),
                 system_info.get("gpu_memory", self.localizer.translate("unknown"))),
                (self.localizer.translate("gpu-driver"),
                 system_info.get("gpu_driver", self.localizer.translate("unknown"))),
                (self.localizer.translate("gpu-temperature"),
                 system_info.get("gpu_temp", self.localizer.translate("unknown")))
            ]
        else:
            hardware_items = [(self.localizer.translate("error"), self.localizer.translate("unable-retrieve-hardware"))]

        hardware_card = self.create_info_card(
            self.localizer.translate("hardware-information"),
            hardware_items,
            ft.Icons.MEMORY
        )

        if "error" not in system_info:
            storage_items = [
                (self.localizer.translate("total-ram"),
                 system_info.get("ram_total", self.localizer.translate("unknown"))),
                (self.localizer.translate("available-ram"),
                 system_info.get("ram_available", self.localizer.translate("unknown"))),
                (self.localizer.translate("ram-usage"),
                 system_info.get("ram_percent", self.localizer.translate("unknown"))),
                (self.localizer.translate("total-disk"),
                 system_info.get("disk_total", self.localizer.translate("unknown"))),
                (self.localizer.translate("free-disk"),
                 system_info.get("disk_free", self.localizer.translate("unknown"))),
                (self.localizer.translate("disk-usage"),
                 system_info.get("disk_percent", self.localizer.translate("unknown")))
            ]
        else:
            storage_items = [(self.localizer.translate("error"), self.localizer.translate("unable-retrieve-storage"))]

        storage_card = self.create_info_card(
            self.localizer.translate("memory-storage"),
            storage_items,
            ft.Icons.STORAGE
        )

        # Action buttons
        close_button = ft.TextButton(
            text=self.localizer.translate("close"),
            style=ft.ButtonStyle(
                padding=ft.padding.symmetric(horizontal=24, vertical=12),
                color="white",
                bgcolor=ft.Colors.with_opacity(0.1, "white"),
                elevation=2,
                text_style=ft.TextStyle(
                    size=16,
                    weight=ft.FontWeight.W_500
                ),
                shape=ft.RoundedRectangleBorder(radius=8),
                overlay_color={
                    ft.ControlState.HOVERED: ft.Colors.with_opacity(0.05, "white"),
                    ft.ControlState.PRESSED: ft.Colors.with_opacity(0.1, "white")
                }
            ),
            on_click=lambda e: self.page.close(self.info_dialog)
        )

        copy_button = ft.TextButton(
            text=self.localizer.translate("copy-info"),
            icon=ft.Icons.COPY,
            style=ft.ButtonStyle(
                padding=ft.padding.symmetric(horizontal=24, vertical=12),
                color="white",
                bgcolor=PURPLE,
                elevation=3,
                text_style=ft.TextStyle(
                    size=16,
                    weight=ft.FontWeight.W_600
                ),
                shape=ft.RoundedRectangleBorder(radius=8),
                overlay_color={
                    ft.ControlState.HOVERED: ft.Colors.with_opacity(0.1, "white"),
                    ft.ControlState.PRESSED: ft.Colors.with_opacity(0.2, "white")
                },
                icon_size=20
            ),
            on_click=self.copy_system_info
        )

        content = ft.Container(
            content=ft.Column([
                stewart_card,
                system_card,
                hardware_card,
                storage_card
            ], spacing=8, scroll=ft.ScrollMode.AUTO),
            height=500,
            width=850
        )

        self.info_dialog = ft.AlertDialog(
            title=ft.Container(
                content=ft.Row([
                    ft.Icon(ft.Icons.INFO_OUTLINE, color=PURPLE, size=28),
                    ft.Text(
                        self.localizer.translate("system-app-information"),
                        size=20,
                        weight=ft.FontWeight.W_600,
                        color="white"
                    )
                ], spacing=12, alignment=ft.MainAxisAlignment.START),
                padding=ft.padding.only(bottom=8)
            ),
            content=content,
            actions=[
                ft.Container(
                    content=ft.Row([
                        copy_button,
                        ft.Container(width=12),
                        close_button
                    ], alignment=ft.MainAxisAlignment.END, spacing=0),
                    padding=ft.padding.only(top=16)
                )
            ],
            actions_alignment=ft.MainAxisAlignment.END,
            modal=True,
            bgcolor=ft.Colors.with_opacity(0.95, ft.Colors.GREY_900),
            surface_tint_color=ft.Colors.TRANSPARENT,
            shape=ft.RoundedRectangleBorder(radius=16),
            elevation=8
        )

    def create_remove_dialog(self):
        self.remove_no_button = ft.TextButton(
            text=self.localizer.translate("no"),
            style=ft.ButtonStyle(
                padding=ft.padding.symmetric(horizontal=24, vertical=12),
                color="white",
                bgcolor=ft.Colors.with_opacity(0.1, "white"),
                elevation=2,
                text_style=ft.TextStyle(
                    size=16,
                    weight=ft.FontWeight.W_500
                ),
                shape=ft.RoundedRectangleBorder(radius=8),
                overlay_color={
                    ft.ControlState.HOVERED: ft.Colors.with_opacity(0.05, "white"),
                    ft.ControlState.PRESSED: ft.Colors.with_opacity(0.1, "white")
                }
            ),
            on_click=None
        )

        self.remove_yes_button = ft.TextButton(
            text=self.localizer.translate("yes"),
            style=ft.ButtonStyle(
                padding=ft.padding.symmetric(horizontal=24, vertical=12),
                color="white",
                bgcolor=RED,
                elevation=3,
                text_style=ft.TextStyle(
                    size=16,
                    weight=ft.FontWeight.W_600
                ),
                shape=ft.RoundedRectangleBorder(radius=8),
                overlay_color={
                    ft.ControlState.HOVERED: ft.Colors.with_opacity(0.1, "white"),
                    ft.ControlState.PRESSED: ft.Colors.with_opacity(0.2, "white")
                }
            ),
            on_click=None
        )

        content = ft.Column(
            controls=[
                ft.Icon(
                    name=ft.Icons.WARNING_AMBER_ROUNDED,
                    color=ft.Colors.AMBER_400,
                    size=52
                ),
                ft.Container(height=16),  # Spacer
                ft.Text(
                    self.localizer.translate("uninstall-dialog"),
                    size=16,
                    color=ft.Colors.with_opacity(0.8, "white"),
                    text_align=ft.TextAlign.CENTER,
                    weight=ft.FontWeight.W_400
                )
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=0,
            height=100
        )

        self.remove_dialog = ft.AlertDialog(
            title=ft.Container(
                content=ft.Text(
                    self.localizer.translate("confirm-uninstall"),
                    size=20,
                    weight=ft.FontWeight.W_600,
                    color="white",
                    text_align=ft.TextAlign.CENTER
                ),
                padding=ft.padding.only(bottom=8)
            ),
            content=ft.Container(
                content=content,
                padding=ft.padding.symmetric(horizontal=16, vertical=8),
                width=320
            ),
            actions=[
                ft.Container(
                    content=ft.Row(
                        controls=[
                            self.remove_no_button,
                            ft.Container(width=12),  # Spacer between buttons
                            self.remove_yes_button
                        ],
                        alignment=ft.MainAxisAlignment.END,
                        spacing=0
                    ),
                    padding=ft.padding.only(top=16)
                )
            ],
            actions_alignment=ft.MainAxisAlignment.END,
            modal=True,
            bgcolor=ft.Colors.with_opacity(0.95, ft.Colors.GREY_900),  # Subtle dark background
            surface_tint_color=ft.Colors.TRANSPARENT,
            shape=ft.RoundedRectangleBorder(radius=16),
            elevation=8
        )

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

        self.info_bar = ft.IconButton(
            icon=ft.Icons.INFO_OUTLINED,
            on_click=None,
            style=ft.ButtonStyle(
                padding=0,
                color="white",
                icon_size=30
            )
        )

        self.appbar = ft.AppBar(
            title=self.app_bar_file_pick,
            center_title=True,
            actions=[
                self.info_bar,
                self.language_change
            ],
        )

    def create_progress_bar(self):
        self.progress_bar = ft.ProgressBar(
            width=400,
            color=PURPLE,
            bar_height=40,
            value=0,
            visible=False
        )

    def create_overview(self):
        self.overview = ft.Markdown(scale=1.3)

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
            scale=1.25,
            style=ft.ButtonStyle(
                padding=ft.padding.symmetric(horizontal=24, vertical=12),
                color="white",
                bgcolor=PURPLE,
                elevation=3,
                text_style=ft.TextStyle(
                    size=16,
                    weight=ft.FontWeight.W_600
                ),
                shape=ft.RoundedRectangleBorder(radius=8),
                overlay_color={
                    ft.ControlState.HOVERED: ft.Colors.with_opacity(0.1, "white"),
                    ft.ControlState.PRESSED: ft.Colors.with_opacity(0.2, "white")
                },
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
            scale=1.25,
            style=ft.ButtonStyle(
                padding=ft.padding.symmetric(horizontal=24, vertical=12),
                color="white",
                bgcolor=ft.Colors.with_opacity(0.1, "white"),
                elevation=3,
                text_style=ft.TextStyle(
                    size=16,
                    weight=ft.FontWeight.W_600
                ),
                shape=ft.RoundedRectangleBorder(radius=8),
                overlay_color={
                    ft.ControlState.HOVERED: ft.Colors.with_opacity(0.1, "white"),
                    ft.ControlState.PRESSED: ft.Colors.with_opacity(0.2, "white")
                },
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
            scale=1.25,
            style=ft.ButtonStyle(
                padding=ft.padding.symmetric(horizontal=24, vertical=12),
                color="white",
                bgcolor=PURPLE,
                elevation=3,
                text_style=ft.TextStyle(
                    size=16,
                    weight=ft.FontWeight.W_600
                ),
                shape=ft.RoundedRectangleBorder(radius=8),
                overlay_color={
                    ft.ControlState.HOVERED: ft.Colors.with_opacity(0.1, "white"),
                    ft.ControlState.PRESSED: ft.Colors.with_opacity(0.2, "white")
                },
                icon_size=25
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
                self.progress.update_info(self.localizer.translate("success-python"))

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
        self.ui_components.create_remove_dialog()
        self.ui_components.create_info_dialog()

        self._bind_event_handlers()

    def _bind_event_handlers(self):
        for item in self.ui_components.language_items:
            item.on_click = self.change_locale

        self.ui_components.info_bar.on_click = self.launch_info_dialog
        self.ui_components.install_button.on_click = self.install
        self.ui_components.update_button.on_click = self.update
        self.ui_components.remove_button.on_click = lambda e: self.page.open(self.ui_components.remove_dialog)
        self.ui_components.remove_no_button.on_click = lambda e: self.page.close(self.ui_components.remove_dialog)
        self.ui_components.remove_yes_button.on_click = self.uninstall

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

        if remote_version != version_info["version"] or self.version_manager.has_relevant_updates(version_info["path"], self.git_manager.excluded_dirs):
            self._handle_update_available(version_info, remote_version)
        else:
            self._handle_current_installation(version_info)

    def _handle_no_installation(self):
        self.no_detect = True
        self.update_exists = False

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

        if self.local_version != self.remote_version:
            self.ui_components.overview.value = self.localizer.translate(
                "update-from",
                local_version=self.local_version,
                remote_version=self.remote_version
            )
        else:
            self.ui_components.overview.value = self.localizer.translate(
                "bugfix",
                local_version=self.local_version,
            )

        self.ui_components.overview.update()

        self.ui_components.app_bar_file_pick.value = version_info["path"]
        self.ui_components.app_bar_file_pick.update()

    def _handle_current_installation(self, version_info):
        self.no_detect = False
        self.update_exists = False

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

    def launch_info_dialog(self, e):
        self.ui_components.local_version = self.local_version
        self.ui_components.remote_version = self.remote_version
        self.ui_components.existing_installation_folder = self.existing_installation_folder
        self.ui_components.page = self.page

        self.ui_components.create_info_dialog()
        self.page.open(self.ui_components.info_dialog)

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
            for directory in self.git_manager.excluded_dirs:
                self.git_manager.skip_work_tree(install_path, directory)

            result = self.git_manager.pull_updates(install_path, self.git_manager.excluded_dirs)
            self.version_manager.update_version_file(str(install_path), e.control.data[0])

            self._update_info(self.localizer.translate("update-successful"))
            self.ui_components.image.src = f"{PROJECT_DIR}/data/assets/stewart_logo.png"
            self.ui_components.image.update()

            self.ui_components.remove_button.disabled = False
            self.ui_components.remove_button.opacity = 1.0
            self.ui_components.remove_button.update()

            self._find_existing_installation()

        except subprocess.CalledProcessError as err:
            self._update_info(self.localizer.translate("update-fail", error=err.stderr))

    def change_locale(self, e):
        if self.installing:
            snack_bar = ft.SnackBar(
                content=ft.Text(self.localizer.translate("change-lang"), color="white", size=18),
                behavior=ft.SnackBarBehavior.FIXED,
                bgcolor=PURPLE,
                duration=2000,
                width=550,
            )
            self.page.open(snack_bar)
            return

        lang = e.control.data
        self.localizer.set_language(lang)
        self._update_ui_text()

    def _update_ui_text(self):
        self.ui_components.remove_yes_button.text = self.localizer.translate("yes")
        self.ui_components.remove_no_button.text = self.localizer.translate("no")
        self.ui_components.remove_dialog.title.content.value = self.localizer.translate("confirm-uninstall")
        self.ui_components.remove_dialog.content.content.controls[2].value = self.localizer.translate(
            "uninstall-dialog")

        self.ui_components.install_button.text = self.localizer.translate("install")
        self.ui_components.remove_button.text = self.localizer.translate("delete")

        self.ui_components.language_change.tooltip = self.localizer.translate("choose-lang")

        if self.no_detect:
            self.ui_components.update_button.text = self.localizer.translate("update")
            self.ui_components.overview.value = self.localizer.translate("found-no-install")
        else:
            if self.update_exists:
                self.ui_components.update_button.text = self.localizer.translate("update")
                if self.local_version != self.remote_version:
                    self.ui_components.overview.value = self.localizer.translate(
                        "update-from",
                        local_version=self.local_version,
                        remote_version=self.remote_version
                    )
                else:
                    self.ui_components.overview.value = self.localizer.translate(
                        "bugfix",
                        local_version=self.local_version,
                    )
            else:
                self.ui_components.update_button.text = self.localizer.translate("launch")
                self.ui_components.overview.value = self.localizer.translate(
                    "found-install",
                    local_version=self.local_version
                )

        self.ui_components.create_info_dialog()

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
            return True
        return False

    def _update_info(self, message):
        self.ui_components.overview.value = message
        self.ui_components.overview.update()

    def install(self, e):
        success = self.file_pick()
        if not success:
            self.ui_components.overview.value = self.localizer.translate("abort-install")
            self.ui_components.overview.update()
            return
        self.start_installation()

    def uninstall(self, e):
        self.page.close(self.ui_components.remove_dialog)

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
                    [self.ui_components.update_button, self.ui_components.install_button,
                     self.ui_components.remove_button],
                    alignment=ft.MainAxisAlignment.CENTER,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=65,
                    expand=True,
                ),
            ],)
        )
        self.page.update()


app = StewartInstaller()
ft.app(app.build_ui)
