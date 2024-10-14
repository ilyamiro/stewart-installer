import subprocess


def run_bash_script(output, github_url):
    try:
        # Clone the GitHub repo
        output.value += f"Cloning repository from {github_url}...\n"
        subprocess.run(f"git clone {github_url} project", shell=True, check=True)
        output.value += "Repository cloned successfully.\n"

        # Navigate into project directory
        os.chdir("project")

        # Run the installation bash script
        output.value += "Running installation script...\n"
        subprocess.run("bash ../install_python.sh", shell=True, check=True)
        output.value += "Installation completed successfully.\n"
    except subprocess.CalledProcessError as e:
        output.value += f"Error: {e}\n"

