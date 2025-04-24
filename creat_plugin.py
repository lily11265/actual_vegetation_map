# -*- coding: utf-8 -*-
"""

 _____         _    _                        _____         _____ 
/  ___|       | |  | |                      |  ___|       /  __ \
\ `--.   ___  | |  | |  ___    ___   _ __   | |__   _ __  | /  \/
 `--. \ / _ \ | |/\| | / _ \  / _ \ | '_ \  |  __| | '_ \ | |    
/\__/ /| (_) |\  /\  /| (_) || (_) || | | | | |___ | | | || \__/\
\____/  \___/  \/  \/  \___/  \___/ |_| |_| \____/ |_| |_| \____/
                                                                 
                                                                
이 스크립트는 도면 자동화 플러그인을 생성하고 패키징하는 도구입니다.
"""

import os
import shutil
import zipfile

def create_plugin_structure():
    """플러그인 디렉토리 구조 생성"""
    
    plugin_dir = "domun_automation_plugin"
    
    # 필요한 디렉토리 생성
    directories = [
        plugin_dir,
        os.path.join(plugin_dir, "resources"),
        os.path.join(plugin_dir, "icons")
    ]
    
    for directory in directories:
        os.makedirs(directory, exist_ok=True)
    
    # __init__.py 파일 복사/생성
    # metadata.txt 파일 복사/생성
    # domun_automation_plugin.py 복사/생성
    # domun_automation_dialog.py 복사/생성
    # domun_automation_dialog_base.ui 복사/생성
    
    print("플러그인 디렉토리 구조 생성 완료")
    
    # 리소스 파일 복사
    # TN_MAPINDX_5K25K.gpkg 파일을 resources 폴더에 복사
    # big_data_land_25000 폴더의 내용을 resources 폴더에 복사
    
    return plugin_dir

def create_icon():
    """기본 아이콘 파일 생성"""
    # 여기서는 기본 아이콘을 생성하거나 복사
    # 실제로는 PNG 파일이 필요함
    pass

def package_plugin(plugin_dir):
    """플러그인을 ZIP 파일로 패키징"""
    zip_filename = f"{plugin_dir}.zip"
    
    with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(plugin_dir):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, os.path.dirname(plugin_dir))
                zipf.write(file_path, arcname)
    
    print(f"플러그인 패키징 완료: {zip_filename}")
    return zip_filename

def install_plugin(zip_filename):
    """플러그인을 QGIS에 설치"""
    import platform
    
    # QGIS 플러그인 디렉토리 경로 확인
    if platform.system() == "Windows":
        plugin_dir = os.path.join(os.path.expanduser("~"), "AppData", "Roaming", "QGIS", "QGIS3", "profiles", "default", "python", "plugins")
    elif platform.system() == "Darwin":  # macOS
        plugin_dir = os.path.join(os.path.expanduser("~"), "Library", "Application Support", "QGIS", "QGIS3", "profiles", "default", "python", "plugins")
    else:  # Linux
        plugin_dir = os.path.join(os.path.expanduser("~"), ".local", "share", "QGIS", "QGIS3", "profiles", "default", "python", "plugins")
    
    # 플러그인 디렉토리가 없으면 생성
    os.makedirs(plugin_dir, exist_ok=True)
    
    # 기존 플러그인 제거
    plugin_name = os.path.splitext(os.path.basename(zip_filename))[0]
    target_dir = os.path.join(plugin_dir, plugin_name)
    
    if os.path.exists(target_dir):
        shutil.rmtree(target_dir)
    
    # 플러그인 압축 해제
    with zipfile.ZipFile(zip_filename, 'r') as zipf:
        zipf.extractall(plugin_dir)
    
    print(f"플러그인 설치 완료: {target_dir}")
    print("QGIS를 재시작하고 플러그인 관리자에서 '도면 자동화 플러그인'을 활성화하세요.")

if __name__ == "__main__":
    plugin_dir = create_plugin_structure()
    create_icon()
    zip_filename = package_plugin(plugin_dir)
    
    # 설치할지 여부 확인
    answer = input("플러그인을 QGIS에 설치하시겠습니까? (y/n): ")
    if answer.lower() == 'y':
        install_plugin(zip_filename)