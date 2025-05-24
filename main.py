import os
import time
import signal
import requests
import threading
import subprocess
import concurrent.futures
import flet as ft
import re


class StewartInstaller:
    GITHUB_URL = "https://github.com/ilyamiro/stewart.git"
    PURPLE = "#6736FD"

    def __init__(self):
        self.installation_folder = os.path.expanduser('~')

        self.progress_bar = ft.ProgressBar(
            width=400,
            color=self.PURPLE,
            bar_height=10
        )
        self.progress_bar.value = 0
        self.progress_bar.visible = False

        self.overview = ft.Markdown(scale=1.2)

        self.image = ft.Image(
            src="data/assets/loading.gif",
            fit=ft.ImageFit.CONTAIN,
            width=450,
            height=450
        )

        self.install_button = ft.TextButton(
            icon=ft.Icons.INSTALL_DESKTOP,
            icon_color="white",
            text="Install",
            scale=1.5,
            style=ft.ButtonStyle(color="white", bgcolor=self.PURPLE, elevation=4, icon_size=20),
            on_click=self.install
        )

        self.pick_dir_button = ft.IconButton(
            icon=ft.Icons.FOLDER_ROUNDED, icon_size=34, icon_color="white",
            on_click=self.file_pick, bgcolor=self.PURPLE
        )

    def launch(self, e):
        subprocess.Popen(
            ["bash", "data/scripts/launch.sh", f"{self.installation_folder}/stewart"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def file_pick(self, e):
        """
        Prompt user to select an installation directory.
        """
        command = ['zenity', '--file-selection', '--title=Choose an installation directory', '--directory']
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        directory = result.stdout.decode('utf-8').strip()

        self.overview.value = f"Chosen install directory: **{directory}**"
        self.overview.update()
        self.installation_folder = directory

    def set_progress(self, value, animate=True):
        """
        Set progress bar to a specific value with optional smooth animation.
        """
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
        """
        Attempt to connect to a given host.
        """
        try:
            requests.get(host, timeout=timeout)
            return True
        except requests.ConnectionError:
            return False

    def internet_connection(self, hosts=None, timeout=3) -> bool:
        """
        Check if there is an active internet connection by attempting to reach multiple hosts.
        """
        if hosts is None:
            hosts = ["https://google.com", "https://github.com"]

        with concurrent.futures.ThreadPoolExecutor() as executor:
            futures = [executor.submit(self.check_host, host, timeout) for host in hosts]
            for future in concurrent.futures.as_completed(futures):
                if future.result():
                    return True
        return False

    def install(self, e):
        self.progress_bar.visible = True
        self.set_progress(0)

        self.info("🌐 Checking internet connection...")
        self.set_progress(0.05)

        if not self.internet_connection():
            self.info("❌ No internet connection. Try again later.")
            return

        self.info("✅ Internet connection established. Proceeding...")
        self.set_progress(0.10)

        try:
            path = os.path.join(self.installation_folder, "stewart")

            self.info("📦 Preparing installation directory...")
            self.set_progress(0.15)

            if os.path.exists(path):
                self.info("📁 Directory already exists, cleaning up...")
                import shutil
                shutil.rmtree(path)

            os.mkdir(path)
            self.set_progress(0.20)

            self.info("🔄 Cloning repository from GitHub...")

            process = subprocess.Popen(
                ["git", "clone", "-b", "development", "--progress", self.GITHUB_URL, path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                bufsize=1
            )

            for line in process.stderr:
                if "Receiving objects" in line:
                    try:
                        progress = int(line.split("%")[0].split()[-1])
                        # Map git progress (0-100%) to our progress range (20-45%)
                        progress_value = 0.20 + (progress * 0.0025)
                        self.set_progress(progress_value, animate=False)

                        self.info(f"📥 Downloading repository... **{progress}%**")
                    except (IndexError, ValueError):
                        pass

            process.wait()

            if process.returncode == 0:
                self.info("✅ Repository cloned successfully.")
                self.set_progress(0.45)
            else:
                self.info("❌ Error during cloning. Try again.")
                return

            self.run_installation_script(path)
        except Exception as err:
            self.info(f"❌ Error: {err}")

    def run_installation_script(self, path):
        """
        Run the installation script for Python3.11 with filtered output
        """
        self.info("🐍 Checking Python 3.11 installation...")
        self.set_progress(0.50)

        process = subprocess.Popen(
            ["bash", "data/scripts/install.sh", path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            bufsize=1
        )

        # Track installation stages
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

            # Filter and display relevant installation messages
            if "Python 3.11 is already installed" in line:
                self.info("✅ Python 3.11 already installed")
                current_stage = "packages_install"
                self.set_progress(progress_stages[current_stage])

            elif "Python 3.11 not found" in line:
                self.info("📦 Installing Python 3.11...")
                current_stage = "python_install"
                self.set_progress(progress_stages[current_stage])

            elif "Detected apt" in line or "Detected dnf" in line or "Detected yum" in line or "Detected pacman" in line or "Detected zypper" in line:
                pkg_manager = line.split("(")[1].split(")")[0] if "(" in line else "system packages"
                self.info(f"🔧 Installing system packages using {pkg_manager}...")

            elif "Installing additional packages" in line:
                self.info("⚙️ Installing additional system dependencies...")
                current_stage = "packages_install"
                self.set_progress(progress_stages[current_stage])

            elif "python3.11 -m venv venv" in line or "Creating virtual environment" in line:
                self.info("🏗️ Setting up Python virtual environment...")
                current_stage = "venv_setup"
                self.set_progress(progress_stages[current_stage])

            elif "pip install -r requirements.txt" in line or "Installing requirements" in line:
                self.info("📋 Installing Python requirements...")
                current_stage = "requirements_install"
                self.set_progress(progress_stages[current_stage])

            elif "Successfully installed" in line:
                # Extract package names from pip success messages
                packages = re.findall(r'Successfully installed (.+)', line)
                if packages:
                    package_list = packages[0].replace('-', ' ').split()[:10]  # Show first 3 packages
                    self.info(f"✅ Installed packages: {', '.join(package_list)} and others...")

            elif "Collecting" in line and "pip" not in line.lower():
                # Show when collecting major packages
                package = line.replace("Collecting ", "").split()[0]
                # if any(pkg in package.lower() for pkg in ['torch', 'numpy', 'requests', 'flet', 'dotenv',]):
                self.info(f"📦 Installing package: **{package}**")

        process.wait()

        self.install_button.icon = ft.Icons.START
        self.install_button.text = "Launch"
        self.install_button.on_click = self.launch

        self.install_button.update()

        if process.returncode == 0:
            self.info("**Installation completed successfully**")
            current_stage = "complete"
        else:
            self.info("❌ There was an error during installation. Please try again.")

        self.set_progress(progress_stages.get(current_stage, 1.0))

    def exit(self):
        os.kill(os.getpid(), signal.SIGKILL)

    def build_ui(self, page: ft.Page):
        page.window.height = 620
        page.window.width = 1080
        page.title = "Stewart"
        page.on_close = self.exit

        page.add(
            ft.Column(
                [
                    ft.Row([self.image], alignment=ft.MainAxisAlignment.CENTER),
                    ft.Row(
                        [self.install_button, self.pick_dir_button],
                        alignment=ft.MainAxisAlignment.CENTER,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        expand=True,
                        spacing=28
                    ),
                    ft.Text(),
                    ft.Row([self.progress_bar], alignment=ft.MainAxisAlignment.CENTER),
                    ft.Row([self.overview], alignment=ft.MainAxisAlignment.CENTER),
                ]
            )
        )
        page.update()


def main(page: ft.Page):
    app = StewartInstaller()
    app.build_ui(page)


ft.app(main)