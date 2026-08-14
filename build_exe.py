import os
import sys
import subprocess

def run_cmd(cmd):
    print(f"\n--- Running: {cmd} ---")
    res = subprocess.run(cmd, shell=True)
    if res.returncode != 0:
        print(f"Command failed with exit code {res.returncode}")
        return False
    return True

def main():
    print("==================================================")
    print(" Building ODtech ERP Live Server Desktop (.exe)  ")
    print("==================================================")

    # 1. Install pyinstaller and pywebview
    print("\nInstalling PyInstaller and PyWebView...")
    run_cmd(f'"{sys.executable}" -m pip install pyinstaller pywebview')

    # 2. Build executable using PyInstaller spec
    print("\nBuilding Executable...")
    success = run_cmd(f'"{sys.executable}" -m PyInstaller --noconfirm ODtech_ERP.spec')

    if success and (os.path.exists("dist/ODtech_ERP.exe") or os.path.exists("dist/ODtech_ERP")):
        exe_path = "dist/ODtech_ERP.exe" if os.path.exists("dist/ODtech_ERP.exe") else "dist/ODtech_ERP/ODtech_ERP.exe"
        print("\n==================================================")
        print(" BUILD SUCCESSFUL!")
        print(f" Standalone Live Server Executable ready at:\n {os.path.abspath(exe_path)}")
        print(" Connected to: https://collar-mammal-strike.ngrok-free.dev/")
        print("==================================================")
    else:
        print("\nBuild failed. Please check error messages above.")

if __name__ == '__main__':
    main()
