import PyInstaller.__main__
import os
import shutil

# Dapatkan path absolut ke direktori proyek
project_dir = os.path.abspath(os.path.dirname(__file__))

# Path ke file dan folder yang diperlukan
icon_path = os.path.join(project_dir, 'icon.ico')
main_path = os.path.join(project_dir, 'app.py')
web_path = os.path.join(project_dir, 'web')
platform_tools_path = os.path.join(project_dir, 'platform-tools')

# Pastikan platform-tools ada
if not os.path.exists(platform_tools_path):
    raise Exception("platform-tools folder not found! Please download Android SDK Platform Tools and extract to project directory.")

PyInstaller.__main__.run([
    main_path,
    '--name=SiberProx',
    '--onefile',
    f'--icon={icon_path}',
    '--noconsole',
    '--add-data=web;web',  # Untuk Windows
    '--add-data=platform-tools;platform-tools',  # Tambahkan platform-tools
    # '--add-data=web:web',  # Untuk Linux/Mac
    # '--add-data=platform-tools:platform-tools',  # Untuk Linux/Mac
    '--hidden-import=bottle_websocket',
    '--hidden-import=engineio.async_drivers.threading',
    '--clean',
]) 