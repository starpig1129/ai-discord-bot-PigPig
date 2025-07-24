import requests, zipfile, os, shutil, argparse
from io import BytesIO

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))  # 獲取當前腳本所在的目錄路徑
__version__ = "v2.6.0"  # 當前版本號

GITHUB_API_URL = "https://api.github.com/repos/PigPig-discord-LLM-bot/releases/latest"  # GitHub API 地址,用於獲取最新版本信息
PIGPIG_URL = "https://github.com/PigPig-discord-LLM-bot/archive/"  # 下載 PigPig Bot 的 URL
IGNORE_FILES = [
    "settings.json", ".env", "data/", "systemPrompt.yaml",
    "logs/", "temp/", "__pycache__/", "*.pyc", "models/", 
    "lavalink/", "chromedriver*/", "school", ".git/", ".gitignore"
]  # 忽略的文件和目錄列表

class bcolors:
    WARNING = '\033[93m'  # 警告顏色
    FAIL = '\033[91m'  # 失敗顏色
    OKGREEN = '\033[92m'  # 成功顏色
    ENDC = '\033[0m'  # 顏色結束標記

def check_version(with_msg=False):
    """檢查項目的最新版本。

    Args:
        with_msg (bool): 是否打印消息的選項。

    Returns:
        str: 最新版本號。
    """
    try:
        response = requests.get(GITHUB_API_URL, timeout=30)  # 發送 GET 請求獲取最新版本信息
        response.raise_for_status()
        latest_version = response.json().get("name", __version__)  # 從 JSON 響應中獲取最新版本號,如果獲取失敗則使用當前版本號
        
        if with_msg:
            msg = f"{bcolors.OKGREEN}Your PigPig Bot is up-to-date! - {latest_version}{bcolors.ENDC}" if latest_version == __version__ else \
                  f"{bcolors.WARNING}Your PigPig Bot is not up-to-date! The latest version is {latest_version} and you are currently running version {__version__}\n. Run `python update.py -l` to update your bot!{bcolors.ENDC}"
            print(msg)  # 打印版本檢查消息
        return latest_version
    except Exception as e:
        if with_msg:
            print(f"{bcolors.FAIL}Error checking version: {e}{bcolors.ENDC}")
        return __version__

def download_file(version=None):
    """下載項目的最新版本。

    Args:
        version (str): 要下載的版本號。如果為 None,則下載最新版本。

    Returns:
        requests.Response: 下載的響應對象。
    """
    version = version if version else check_version()  # 如果版本號未指定,則獲取最新版本號
    print(f"Downloading PigPig Bot version: {version}")  # 打印下載的版本號
    
    try:
        response = requests.get(PIGPIG_URL + version + ".zip", timeout=300)  # 下載指定版本的 ZIP 文件
        if response.status_code == 404:
            print(f"{bcolors.FAIL}Warning: Version {version} not found!{bcolors.ENDC}")  # 如果版本不存在,則打印警告消息
            exit(1)  # 退出程序
        response.raise_for_status()
        print("Download Completed")  # 打印下載完成消息
        return response
    except Exception as e:
        print(f"{bcolors.FAIL}Error downloading file: {e}{bcolors.ENDC}")
        exit(1)

def install(response, version):
    """安裝下載的項目版本。

    Args:
        response (requests.Response): 下載的響應對象。
        version (str): 要安裝的版本號。
    """
    user_input = input(f"{bcolors.WARNING}--------------------------------------------------------------------------\n"
                           "Note: Before proceeding, please ensure that there are no personal files or\n" \
                           "sensitive information in the directory you're about to delete. This action\n" \
                           "will preserve settings.json, .env, and data/ directory, but other files\n" \
                           f"will be replaced. {bcolors.ENDC} Continue with caution? (Y/n) ")  # 提示用戶確認是否繼續安裝
        
    if user_input.lower() in ["y", "yes", ""]:
        print("Installing ...")  # 打印安裝中消息
        try:
            zfile = zipfile.ZipFile(BytesIO(response.content))  # 創建 ZipFile 對象
            zfile.extractall(ROOT_DIR)  # 解壓 ZIP 文件到當前目錄

            version_clean = version.replace("v", "")  # 去掉版本號前面的 "v"
            
            # 嘗試不同的可能目錄名稱
            possible_dirs = [
                f"PigPig-discord-LLM-bot-{version_clean}",
                f"PigPig-discord-LLM-bot-{version}",
                "PigPig-discord-LLM-bot-main"
            ]
            
            source_dir = None
            for dir_name in possible_dirs:
                potential_path = os.path.join(ROOT_DIR, dir_name)
                if os.path.exists(potential_path):
                    source_dir = potential_path
                    break
            
            if not source_dir:
                print(f"{bcolors.FAIL}Error: Could not find extracted directory{bcolors.ENDC}")
                return
            
            print(f"Found source directory: {source_dir}")
            
            # 刪除舊文件（除了忽略文件）
            for filename in os.listdir(ROOT_DIR):
                if filename in IGNORE_FILES or filename.startswith('.') or filename == os.path.basename(source_dir):
                    continue  # 忽略指定的文件和目錄

                file_path = os.path.join(ROOT_DIR, filename)
                try:
                    if os.path.isdir(file_path):
                        shutil.rmtree(file_path)  # 刪除目錄
                        print(f"Removed directory: {filename}")
                    else:
                        os.remove(file_path)  # 刪除文件
                        print(f"Removed file: {filename}")
                except Exception as e:
                    print(f"{bcolors.WARNING}Warning: Could not remove {filename}: {e}{bcolors.ENDC}")
            
            # 移動新文件
            for filename in os.listdir(source_dir):
                if filename in IGNORE_FILES:
                    continue  # 不覆蓋忽略的文件
                
                source_path = os.path.join(source_dir, filename)
                dest_path = os.path.join(ROOT_DIR, filename)
                
                try:
                    if os.path.exists(dest_path):
                        if os.path.isdir(dest_path):
                            shutil.rmtree(dest_path)
                        else:
                            os.remove(dest_path)
                    
                    shutil.move(source_path, dest_path)  # 將源代碼目錄中的文件移動到當前目錄
                    print(f"Updated: {filename}")
                except Exception as e:
                    print(f"{bcolors.WARNING}Warning: Could not update {filename}: {e}{bcolors.ENDC}")
            
            # 清理解壓目錄
            try:
                shutil.rmtree(source_dir)  # 刪除源代碼目錄
            except Exception as e:
                print(f"{bcolors.WARNING}Warning: Could not clean up {source_dir}: {e}{bcolors.ENDC}")
            
            print(f"{bcolors.OKGREEN}Version {version} installed Successfully! Run `python main.py` to start your bot{bcolors.ENDC}")  # 打印安裝成功消息
            
        except Exception as e:
            print(f"{bcolors.FAIL}Error during installation: {e}{bcolors.ENDC}")
    else:
        print("Update canceled!")  # 打印更新取消消息

def parse_args():
    """解析命令行參數。"""
    parser = argparse.ArgumentParser(description='Update script for PigPig Discord Bot.')  # 創建參數解析器
    parser.add_argument('-c', '--check', action='store_true', help='Check the current version of the PigPig Bot')  # 添加 -c 或 --check 參數,用於檢查當前版本
    parser.add_argument('-v', '--version', type=str, help='Install the specified version of the PigPig Bot')  # 添加 -v 或 --version 參數,用於安裝指定版本
    parser.add_argument('-l', '--latest', action='store_true', help='Install the latest version of the PigPig Bot from Github')  # 添加 -l 或 --latest 參數,用於安裝最新版本
    parser.add_argument('-b', '--beta', action='store_true', help='Install the beta version of the PigPig Bot from Github')  # 添加 -b 或 --beta 參數,用於安裝 beta 版本
    return parser.parse_args()  # 返回解析後的參數

def main():
    """主函數。"""
    args = parse_args()  # 解析命令行參數

    if args.check:
        check_version(with_msg=True)  # 檢查當前版本並打印消息
        
    elif args.version:
        version = args.version  # 獲取指定的版本號
        response = download_file(version)  # 下載指定版本
        install(response, version)  # 安裝指定版本
        
    elif args.latest:
        response = download_file()  # 下載最新版本
        version = check_version()  # 獲取最新版本號
        install(response, version)  # 安裝最新版本
        
    elif args.beta:
        response = download_file("refs/heads/beta")  # 下載 beta 版本
        install(response, "beta")  # 安裝 beta 版本

    else:
        print(f"{bcolors.FAIL}No arguments provided. Run `python update.py -h` for help.{bcolors.ENDC}")  # 打印缺少參數的錯誤消息

if __name__ == "__main__":
    main()  # 運行主函數