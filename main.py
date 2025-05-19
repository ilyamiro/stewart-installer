import os
import time
import signal
import requests
import threading
import subprocess
import concurrent.futures
import flet as ft


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

        self.run_button = ft.TextButton(
            icon=ft.Icons.START,
            icon_color="white",
            text="Launch",
            scale=1.5,
            style=ft.ButtonStyle(color="white", bgcolor=self.PURPLE, elevation=4, icon_size=25),
            on_click=self.launch
        )

        self.install_button = ft.TextButton(
            icon=ft.Icons.INSTALL_DESKTOP,
            icon_color="white",
            text="Install",
            scale=1.5,
            style=ft.ButtonStyle(color="white", bgcolor=self.PURPLE, elevation=4, icon_size=25),
            on_click=self.install
        )

        self.pick_dir_button = ft.IconButton(
            icon=ft.Icons.FOLDER_ROUNDED, icon_size=34, icon_color="white",
            on_click=self.file_pick, bgcolor=self.PURPLE
        )

    def launch(self, e):
        subprocess.Popen(
            ["bash", "data/scripts/launch.sh", self.installation_folder],
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

    def increase_progress(self, percent):
        """
        Increase progress bar by a given percent.
        """

        def count():
            current = self.progress_bar.value
            for i in range(1, percent + 1):
                self.progress_bar.value = current + i * 0.01
                time.sleep(0.15)
                self.progress_bar.update()

        thread = threading.Thread(target=count)
        thread.start()

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

        self.info("Checking internet connection...")
        self.increase_progress(10)

        if not self.internet_connection():
            self.info("No internet connection. Try again later.")
            return

        self.info("Internet connection established. Proceeding...")
        time.sleep(0.5)

        try:
            path = os.path.join(self.installation_folder, "stewart")

            self.info("Cloning GitHub repository. Progress: 0%")

            os.mkdir(path)

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
                        self.progress_bar.value = 0.20 + progress * 0.0025
                        self.progress_bar.update()

                        self.info(f"Cloning GitHub repository. Progress: **{progress}%**")
                    except IndexError:
                        pass

            process.wait()

            if process.returncode == 0:
                self.info("Repository cloned successfully.")

            else:
                self.info("Error during cloning. Try again.")
                return

            self.run_installation_script(path)
        except Exception as err:
            self.info(f"Error: {err}")

    def run_installation_script(self, path):
        """
        Run the installation script for Python3.11
        """
        self.info("Running additional packages installation script...")
        self.increase_progress(15)

        process = subprocess.Popen(
            ["bash", "data/scripts/install_python.sh", path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            bufsize=1
        )

        for line in process.stdout:
            self.info(line)

        process.wait()

        if process.returncode == 0:
            self.info("**Installation completed successfully.**\n")
        else:
            self.info("There was an error during installation. Try again.")

        self.progress_bar.value = 1
        self.progress_bar.update()

    def build_ui(self, page: ft.Page):
        page.window.height = 620
        page.window.width = 1080
        page.title = "Stewart"

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
