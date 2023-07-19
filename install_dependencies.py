import subprocess
import pkg_resources


def run_legacy_pip():
    pip_version = pkg_resources.get_distribution("pip").version
    major, minor, _ = map(int, pip_version.split('.'))
    if major >= 20 and minor >= 3:
        subprocess.check_call([
            "pip3", "install", "--use-deprecated=legacy-resolver",
            "-r", "/tmp/requirements.txt", "--no-cache-dir"
        ])
    else:
        subprocess.check_call([
            "pip3", "install", "-r", "/tmp/requirements.txt", "--no-cache-dir"
        ])


if __name__ == "__main__":
    run_legacy_pip()
