from google import genai
from google.genai import types
from google.genai.types import Tool, GenerateContentConfig, GoogleSearch
import asyncio
from addons.settings import TOKENS
from gpt.vision_tool import image_to_base64
import tempfile
import logging
import hashlib
import time
import datetime
import pathlib
import httpx
from typing import Optional, Dict, Any, List, Type
from pydantic import BaseModel

# Initialize the Gemini model
tokens = TOKENS()

# 設置日誌
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

try:
    client = genai.Client(api_key=tokens.gemini_api_key)
    model_id = "gemini-2.0-flash"
    
    google_search_tool = Tool(
        google_search = GoogleSearch()
    )
    
    logger.info("Gemini API 客戶端初始化成功")
except Exception as e:
    logger.error(f"Gemini API 客戶端初始化失敗: {e}")
    raise

class GeminiError(Exception):
    pass

class GeminiCacheManager:
    """Gemini API 顯式快取管理器
    
    基於官方 Gemini API 文檔實現的快取系統，用於提升性能並降低 API 調用成本。
    支援快取大小限制和主動清理機制。
    """
    
    def __init__(self, client: genai.Client, max_cache_count: int = 50):
        self.client = client
        self.active_caches: Dict[str, Any] = {}
        self.cache_metadata: Dict[str, Dict[str, Any]] = {}
        self.logger = logging.getLogger(__name__)
        
        # 快取大小限制和清理設定
        self.max_cache_count = max_cache_count
        self.cache_access_times: Dict[str, float] = {}  # 快取存取時間記錄
        self.cleanup_threshold = max(int(max_cache_count * 0.8), 1)  # 80% 時開始清理
        
    def _generate_cache_key(self, system_instruction: str, contents_hash: str = "") -> str:
        """生成快取鍵值
        
        Args:
            system_instruction: 系統指令
            contents_hash: 內容哈希值
            
        Returns:
            str: 快取鍵值
        """
        hash_input = f"{system_instruction}_{contents_hash}"
        return hashlib.md5(hash_input.encode('utf-8')).hexdigest()[:16]
    
    def create_cache(self,
                    model: str,
                    system_instruction: str,
                    contents: List[Any] = None,
                    ttl: str = "3600s",
                    display_name: str = None) -> Optional[Any]:
        """創建顯式快取
        
        Args:
            model: 模型名稱（必須使用明確版本，如 'models/gemini-2.0-flash-001'）
            system_instruction: 系統指令
            contents: 要快取的內容列表（可包含上傳的檔案）
            ttl: 存留時間（如 "300s", "1h"）
            display_name: 顯示名稱
            
        Returns:
            快取物件或 None（如果創建失敗）
        """
        try:
            # 檢查快取大小限制，必要時清理
            if len(self.active_caches) >= self.cleanup_threshold:
                self._cleanup_least_used_caches()
            
            # 生成快取鍵值
            contents_hash = str(hash(str(contents))) if contents else ""
            cache_key = self._generate_cache_key(system_instruction, contents_hash)
            
            # 檢查是否已存在有效快取
            existing_cache = self.get_cache_by_key(cache_key)
            if existing_cache:
                self.logger.info(f"使用現有快取: {cache_key}")
                # 更新存取時間
                self.cache_access_times[cache_key] = time.time()
                return existing_cache
            
            # 準備快取內容
            cache_contents = contents if contents else []
            
            if display_name is None:
                display_name = f'discord_bot_cache_{cache_key}'
            
            # 使用官方文檔格式創建快取
            cache = self.client.caches.create(
                model=model,
                config=types.CreateCachedContentConfig(
                    display_name=display_name,
                    system_instruction=system_instruction,
                    contents=cache_contents,
                    ttl=ttl,
                )
            )
            
            # 儲存快取資訊
            self.active_caches[cache_key] = cache
            self.cache_metadata[cache_key] = {
                'cache_name': cache.name,
                'created_time': time.time(),
                'ttl': ttl,
                'display_name': display_name,
                'system_instruction': system_instruction,
                'model': model
            }
            self.cache_access_times[cache_key] = time.time()
            
            self.logger.info(f"成功創建新快取: {cache_key} (TTL: {ttl}), 當前快取數量: {len(self.active_caches)}")
            return cache
            
        except Exception as e:
            self.logger.error(f"創建快取失敗: {str(e)}")
            return None
    
    def get_cache_by_key(self, cache_key: str) -> Optional[Any]:
        """根據鍵值獲取快取
        
        Args:
            cache_key: 快取鍵值
            
        Returns:
            快取物件或 None
        """
        if cache_key in self.active_caches:
            try:
                cache = self.active_caches[cache_key]
                # 嘗試獲取快取元數據以驗證是否仍然有效
                cache_info = self.client.caches.get(name=cache.name)
                # 更新存取時間
                self.cache_access_times[cache_key] = time.time()
                return cache
            except Exception as e:
                # 快取可能已過期或無效，清理本地記錄
                self.logger.warning(f"快取 {cache_key} 已無效: {str(e)}")
                self._cleanup_cache_record(cache_key)
                
        return None
    
    def find_cache_by_system_instruction(self, system_instruction: str) -> Optional[Any]:
        """根據系統指令尋找現有快取
        
        Args:
            system_instruction: 系統指令
            
        Returns:
            快取物件或 None
        """
        for cache_key, metadata in self.cache_metadata.items():
            if metadata.get('system_instruction') == system_instruction:
                return self.get_cache_by_key(cache_key)
        return None
    
    def generate_with_cache(self,
                           model: str,
                           contents: Any,
                           config: types.GenerateContentConfig) -> Any:
        """使用快取生成內容
        
        Args:
            model: 模型名稱
            contents: 用戶輸入內容
            config: 生成配置（包含快取名稱等）
            
        Returns:
            生成的回應流
        """
        try:
            
            return self.client.models.generate_content(
                model=model,
                contents=contents,
                config=config
            )
            
        except Exception as e:
            self.logger.error(f"使用快取生成內容失敗: {str(e)}")
            raise GeminiError(f"快取生成失敗: {str(e)}")
    
    def generate_stream_with_cache(self,
                                  model: str,
                                  contents: Any,
                                  config: types.GenerateContentConfig) -> Any:
        """使用快取生成流式內容
        
        Args:
            model: 模型名稱
            contents: 用戶輸入內容
            config: 生成配置（包含快取名稱等）
            
        Returns:
            生成的回應流
        """
        try:

            return self.client.models.generate_content_stream(
                model=model,
                contents=contents,
                config=config
            )
            
        except Exception as e:
            self.logger.error(f"使用快取生成流式內容失敗: {str(e)}")
            raise GeminiError(f"快取流式生成失敗: {str(e)}")
    
    def update_cache_ttl(self, cache_key: str, ttl: str = None, expire_time: datetime.datetime = None) -> bool:
        """更新快取的TTL或到期時間
        
        Args:
            cache_key: 快取鍵值
            ttl: 新的TTL值（如 "300s"）
            expire_time: 明確的到期時間（timezone-aware datetime）
            
        Returns:
            bool: 更新是否成功
        """
        try:
            if cache_key not in self.active_caches:
                return False
                
            cache = self.active_caches[cache_key]
            
            # 準備更新配置
            update_config_kwargs = {}
            if ttl:
                update_config_kwargs['ttl'] = ttl
            elif expire_time:
                update_config_kwargs['expire_time'] = expire_time
            else:
                return False
            
            update_config = types.UpdateCachedContentConfig(**update_config_kwargs)
            
            self.client.caches.update(
                name=cache.name,
                config=update_config
            )
            
            # 更新本地元數據
            if ttl:
                self.cache_metadata[cache_key]['ttl'] = ttl
            
            self.logger.info(f"成功更新快取: {cache_key}")
            return True
            
        except Exception as e:
            self.logger.error(f"更新快取失敗: {str(e)}")
            return False
    
    def delete_cache(self, cache_key: str) -> bool:
        """刪除快取
        
        Args:
            cache_key: 快取鍵值
            
        Returns:
            bool: 刪除是否成功
        """
        try:
            if cache_key in self.active_caches:
                cache = self.active_caches[cache_key]
                self.client.caches.delete(cache.name)
                
                # 清理本地記錄
                self._cleanup_cache_record(cache_key)
                
                self.logger.info(f"成功刪除快取: {cache_key}")
                return True
                
        except Exception as e:
            self.logger.error(f"刪除快取失敗: {str(e)}")
            
        return False
    
    def list_all_caches(self) -> List[Any]:
        """列出所有快取
        
        Returns:
            List[Any]: 快取列表
        """
        try:
            return list(self.client.caches.list())
        except Exception as e:
            self.logger.error(f"列出快取失敗: {str(e)}")
            return []
    
    def cleanup_expired_caches(self) -> int:
        """清理所有本地記錄中已無效的快取
        
        Returns:
            int: 清理的快取數量
        """
        cleaned_count = 0
        keys_to_clean = []
        
        for cache_key in list(self.active_caches.keys()):
            try:
                cache = self.active_caches[cache_key]
                # 嘗試獲取快取資訊以驗證是否仍然有效
                self.client.caches.get(name=cache.name)
            except:
                # 快取已無效
                keys_to_clean.append(cache_key)
        
        for cache_key in keys_to_clean:
            self._cleanup_cache_record(cache_key)
            cleaned_count += 1
        
        if cleaned_count > 0:
            self.logger.info(f"清理了 {cleaned_count} 個無效快取記錄")
            
        return cleaned_count
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """獲取快取統計資訊
        
        Returns:
            dict: 快取統計資訊
        """
        return {
            'local_cache_count': len(self.active_caches),
            'cache_keys': list(self.active_caches.keys()),
            'cache_metadata': self.cache_metadata
        }
    
    def _cleanup_cache_record(self, cache_key: str) -> None:
        """清理本地快取記錄
        
        Args:
            cache_key: 快取鍵值
        """
        if cache_key in self.active_caches:
            del self.active_caches[cache_key]
        if cache_key in self.cache_metadata:
            del self.cache_metadata[cache_key]
        if cache_key in self.cache_access_times:
            del self.cache_access_times[cache_key]
    
    def _cleanup_least_used_caches(self) -> int:
        """清理最少使用的快取
        
        Returns:
            int: 清理的快取數量
        """
        cleaned_count = 0
        
        try:
            # 如果快取數量未超過限制，不執行清理
            if len(self.active_caches) < self.cleanup_threshold:
                return 0
            
            # 計算需要清理的數量（清理到最大限制的60%）
            target_count = max(int(self.max_cache_count * 0.6), 1)
            cleanup_count = len(self.active_caches) - target_count
            
            if cleanup_count <= 0:
                return 0
            
            # 按存取時間排序，清理最舊的快取
            cache_items = []
            for cache_key in self.active_caches.keys():
                access_time = self.cache_access_times.get(cache_key, 0)
                cache_items.append((access_time, cache_key))
            
            # 排序（最舊的在前）
            cache_items.sort(key=lambda x: x[0])
            
            # 清理最舊的快取
            for i in range(min(cleanup_count, len(cache_items))):
                _, cache_key = cache_items[i]
                if self.delete_cache(cache_key):
                    cleaned_count += 1
            
            self.logger.info(f"主動清理了 {cleaned_count} 個最少使用的快取，當前快取數量: {len(self.active_caches)}")
            
        except Exception as e:
            self.logger.error(f"清理最少使用的快取失敗: {str(e)}")
        
        return cleaned_count
    
    def force_cleanup_all_caches(self) -> int:
        """強制清理所有快取
        
        Returns:
            int: 清理的快取數量
        """
        cleaned_count = 0
        cache_keys = list(self.active_caches.keys())
        
        for cache_key in cache_keys:
            if self.delete_cache(cache_key):
                cleaned_count += 1
        
        self.logger.warning(f"強制清理了所有快取，共 {cleaned_count} 個")
        return cleaned_count
    
    def get_cache_size_info(self) -> Dict[str, Any]:
        """獲取快取大小資訊
        
        Returns:
            Dict[str, Any]: 快取大小統計
        """
        return {
            'current_count': len(self.active_caches),
            'max_count': self.max_cache_count,
            'cleanup_threshold': self.cleanup_threshold,
            'usage_ratio': len(self.active_caches) / self.max_cache_count if self.max_cache_count > 0 else 0,
            'needs_cleanup': len(self.active_caches) >= self.cleanup_threshold
        }

# 初始化全域快取管理器
cache_manager: Optional[GeminiCacheManager] = None

def initialize_cache_manager(max_cache_count: int = 50):
    """初始化全域快取管理器"""
    global cache_manager
    if cache_manager is None:
        cache_manager = GeminiCacheManager(client, max_cache_count)
        logger.info(f"全域快取管理器初始化完成，最大快取數量: {max_cache_count}")
    return cache_manager

def get_cache_manager() -> Optional[GeminiCacheManager]:
    """獲取快取管理器實例"""
    global cache_manager
    if cache_manager is None:
        cache_manager = initialize_cache_manager()
    return cache_manager

def _download_and_process_pdf(pdf_url_or_path: str) -> pathlib.Path:
    """下載並處理 PDF 檔案
    
    Args:
        pdf_url_or_path: PDF 檔案的 URL 或本地路徑
        
    Returns:
        pathlib.Path: 本地 PDF 檔案路徑
        
    Raises:
        Exception: 如果下載或處理失敗
    """
    try:
        # 檢查是否為 URL
        if pdf_url_or_path.startswith(('http://', 'https://')):
            # 從 URL 下載 PDF
            logger.info(f"正在從 URL 下載 PDF: {pdf_url_or_path}")
            
            # 產生暫存檔案名稱
            url_hash = hashlib.md5(pdf_url_or_path.encode()).hexdigest()[:8]
            temp_filename = f"pdf_{url_hash}_{int(time.time())}.pdf"
            file_path = pathlib.Path(tempfile.gettempdir()) / temp_filename
            
            # 使用 httpx 下載檔案
            with httpx.Client(timeout=30.0) as client:
                response = client.get(pdf_url_or_path)
                response.raise_for_status()
                
                # 驗證內容類型
                content_type = response.headers.get('content-type', '').lower()
                if 'pdf' not in content_type and not pdf_url_or_path.lower().endswith('.pdf'):
                    logger.warning(f"檔案可能不是 PDF 格式，Content-Type: {content_type}")
                
                # 寫入檔案
                file_path.write_bytes(response.content)
                logger.info(f"PDF 下載成功，儲存至: {file_path}")
                
        else:
            # 本地檔案路徑
            file_path = pathlib.Path(pdf_url_or_path)
            if not file_path.exists():
                raise FileNotFoundError(f"PDF 檔案不存在: {pdf_url_or_path}")
            if not file_path.suffix.lower() == '.pdf':
                raise ValueError(f"檔案不是 PDF 格式: {pdf_url_or_path}")
                
        return file_path
        
    except httpx.RequestError as e:
        raise Exception(f"下載 PDF 檔案失敗: {str(e)}")
    except httpx.HTTPStatusError as e:
        raise Exception(f"HTTP 錯誤 {e.response.status_code}: 無法下載 PDF 檔案")
    except Exception as e:
        raise Exception(f"處理 PDF 檔案失敗: {str(e)}")

async def _upload_pdf_files(pdf_inputs) -> List[Any]:
    """處理 PDF 檔案上傳（異步版本）
    
    Args:
        pdf_inputs: PDF 輸入（URL、本地路徑或列表）
        
    Returns:
        list: 上傳後的檔案物件列表
    """
    uploaded_files = []
    temp_files = []
    
    try:
        # 統一處理為列表
        if not isinstance(pdf_inputs, list):
            pdf_inputs = [pdf_inputs]
        
        # 並行處理：先下載並準備所有 PDF 檔案
        for i, pdf_input in enumerate(pdf_inputs):
            logger.info(f"正在處理 PDF {i+1}/{len(pdf_inputs)}")
            
            # 下載並處理 PDF（保持同步，因為涉及檔案系統操作）
            local_pdf_path = _download_and_process_pdf(pdf_input)
            temp_files.append(local_pdf_path)
        
        # 使用 asyncio.to_thread() 並行上傳所有 PDF 檔案
        async def upload_single_pdf(pdf_path, index):
            """上傳單個 PDF 檔案的異步包裝函數"""
            try:
                # 將同步的上傳操作轉為異步
                uploaded_file = await asyncio.to_thread(client.files.upload, file=pdf_path)
                logger.info(f"PDF {index+1} 已成功上傳到 Gemini Files API")
                return uploaded_file
            except Exception as e:
                logger.error(f"PDF {index+1} 上傳失敗: {str(e)}")
                raise
        
        # 並行上傳所有 PDF 檔案
        upload_tasks = [
            upload_single_pdf(pdf_path, i)
            for i, pdf_path in enumerate(temp_files)
        ]
        
        # 等待所有上傳完成
        uploaded_files = await asyncio.gather(*upload_tasks)
        logger.info(f"所有 PDF 檔案已並行上傳完成，共 {len(uploaded_files)} 個")
            
    except Exception as e:
        logger.error(f"PDF 上傳失敗: {str(e)}")
        raise
    finally:
        # 清理暫存檔案（如果是下載的）
        import os
        for temp_path in temp_files:
            try:
                # 只清理暫存目錄中的檔案，避免誤刪用戶檔案
                if str(temp_path).startswith(tempfile.gettempdir()):
                    os.unlink(temp_path)
                    logger.debug(f"已清理暫存 PDF 檔案: {temp_path}")
            except Exception as cleanup_error:
                logger.warning(f"清理暫存 PDF 檔案失敗: {cleanup_error}")
    
    return uploaded_files

def _save_media_to_temp_file(media_data, media_type, index=0):
    """將媒體資料儲存到臨時檔案並返回檔案路徑
    
    Args:
        media_data: 媒體資料物件（PIL Image、音訊資料、影片資料等）
        media_type: 媒體類型 ('image', 'audio', 'video')
        index: 索引號（用於多個檔案）
        
    Returns:
        str: 臨時檔案路徑
    """
    if media_type == 'image':
        # 處理 PIL Image 物件
        suffix = f"_image_{index}.jpg"
        temp_file = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
        media_data.save(temp_file.name, format='JPEG', quality=85)
        temp_file.close()
        return temp_file.name
        
    elif media_type == 'audio':
        # 處理音訊資料
        suffix = f"_audio_{index}.mp3"
        temp_file = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
        
        if isinstance(media_data, bytes):
            # 如果是 bytes 資料
            temp_file.write(media_data)
        elif hasattr(media_data, 'read'):
            # 如果是檔案物件
            temp_file.write(media_data.read())
        else:
            # 其他類型的音訊資料
            temp_file.write(str(media_data).encode())
            
        temp_file.close()
        return temp_file.name
        
    elif media_type == 'video':
        # 處理影片資料
        suffix = f"_video_{index}.mp4"
        temp_file = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
        
        if isinstance(media_data, bytes):
            # 如果是 bytes 資料
            temp_file.write(media_data)
        elif hasattr(media_data, 'read'):
            # 如果是檔案物件
            temp_file.write(media_data.read())
        elif isinstance(media_data, str):
            # 如果意外是檔案路徑，直接返回
            return media_data
        else:
            # 其他類型的影片資料
            temp_file.write(str(media_data).encode())
            
        temp_file.close()
        return temp_file.name
        
    else:
        raise ValueError(f"不支援的媒體類型: {media_type}")

async def _upload_media_files(media_inputs, media_type):
    """統一處理多媒體檔案上傳（異步版本）
    
    Args:
        media_inputs: 媒體輸入（單個物件或列表）
        media_type: 媒體類型 ('image', 'audio', 'video', 'pdf')
        
    Returns:
        list: 上傳後的檔案物件列表
    """
    # PDF 檔案使用專用的處理函數
    if media_type == 'pdf':
        return await _upload_pdf_files(media_inputs)
    
    uploaded_files = []
    temp_files = []
    
    try:
        # 統一處理為列表
        if not isinstance(media_inputs, list):
            media_inputs = [media_inputs]
        
        # 並行處理：先創建所有臨時檔案
        for i, media_data in enumerate(media_inputs):
            temp_path = _save_media_to_temp_file(media_data, media_type, i)
            temp_files.append(temp_path)
        
        # 使用 asyncio.to_thread() 並行上傳所有檔案
        async def upload_single_file(temp_path, index):
            """上傳單個檔案的異步包裝函數"""
            try:
                # 將同步的上傳操作轉為異步
                uploaded_file = await asyncio.to_thread(client.files.upload, file=temp_path)
                logger.info(f"已上傳{media_type} {index+1} 到 Gemini Files API")
                return uploaded_file
            except Exception as e:
                logger.error(f"{media_type} {index+1} 上傳失敗: {str(e)}")
                raise
        
        # 並行上傳所有檔案
        upload_tasks = [
            upload_single_file(temp_path, i)
            for i, temp_path in enumerate(temp_files)
        ]
        
        # 等待所有上傳完成
        uploaded_files = await asyncio.gather(*upload_tasks)
        logger.info(f"所有 {media_type} 檔案已並行上傳完成，共 {len(uploaded_files)} 個")
        
    except Exception as e:
        logger.error(f"{media_type}上傳失敗: {str(e)}")
        raise
    finally:
        # 清理臨時檔案
        import os
        for temp_path in temp_files:
            try:
                os.unlink(temp_path)
            except Exception as cleanup_error:
                logger.warning(f"清理臨時檔案失敗: {cleanup_error}")
    
    return uploaded_files

async def _build_conversation_contents(inst, dialogue_history=None, image_input=None, audio_input=None, video_input=None, pdf_input=None):
    """建構符合官方規範的對話內容結構。
    
    根據 Gemini API 官方文檔建議，使用結構化的對話格式：
    - 每個訊息包含 role 和 parts
    - parts 陣列包含文字、圖片等內容
    
    Args:
        inst: 當前用戶輸入
        dialogue_history: 對話歷史
        image_input: 圖片輸入
        audio_input: 音頻輸入
        video_input: 視頻輸入
        pdf_input: PDF 檔案輸入
        
    Returns:
        list: 符合官方格式的對話內容列表
    """
    contents = []
    
    # 處理多輪對話歷史
    if dialogue_history:
        for msg in dialogue_history:
            # 根據 Google Gemini API 官方標準處理不同角色
            if msg['role'].lower() == 'function':
                # 工具調用結果使用 model 角色，並特殊格式化
                tool_name = msg.get('name', 'unknown_tool')
                tool_content = msg.get('content', '')
                
                # 格式化工具結果為可讀的形式
                formatted_content = f"[工具結果 - {tool_name}]\n{tool_content}"
                
                contents.append({
                    "role": "model",
                    "parts": [{"text": formatted_content}]
                })
            elif msg['role'].lower() in ['user', 'human']:
                contents.append({
                    "role": "user",
                    "parts": [{"text": msg['content']}]
                })
            elif msg['role'].lower() in ['assistant', 'model']:
                contents.append({
                    "role": "model",
                    "parts": [{"text": msg['content']}]
                })
            elif msg['role'].lower() == 'tool':
                # 處理舊格式的工具結果（向後相容性）
                tool_name = msg.get('user_id', 'unknown_tool')
                tool_content = msg.get('content', '')
                formatted_content = f"[工具結果 - {tool_name}]\n{tool_content}"
                
                contents.append({
                    "role": "model",
                    "parts": [{"text": formatted_content}]
                })
    
    # 建構當前用戶輸入的 parts
    current_parts = []
    
    # 處理多媒體輸入 - 使用統一的處理方式
    # 按優先級處理多媒體（PDF > 影片 > 音訊 > 圖片）
    if pdf_input:
        current_parts.append({"text": inst})
        try:
            # 使用統一的多媒體處理函數
            uploaded_pdfs = await _upload_media_files(pdf_input, 'pdf')
            for uploaded_pdf in uploaded_pdfs:
                current_parts.append(uploaded_pdf)
            logger.info("PDF 檔案已添加到對話內容中")
        except Exception as e:
            logger.error(f"PDF 處理失敗，使用降級方案: {str(e)}")
            # 降級：修改文字提示
            current_parts[0] = {"text": f"{inst}\n\n注意: PDF 處理發生錯誤，無法直接分析 PDF 內容"}
            
    elif video_input:
        current_parts.append({"text": inst})
        try:
            # 使用統一的多媒體處理函數
            uploaded_videos = await _upload_media_files(video_input, 'video')
            for uploaded_video in uploaded_videos:
                current_parts.append(uploaded_video)
            logger.info("影片已添加到對話內容中")
        except Exception as e:
            logger.error(f"影片處理失敗，使用降級方案: {str(e)}")
            # 降級：修改文字提示
            current_parts[0] = {"text": f"{inst}\n\n注意: 影片處理發生錯誤，無法直接分析影片內容"}
            
    elif audio_input:
        current_parts.append({"text": f"請分析這個音訊檔案: {inst}"})
        try:
            # 使用統一的多媒體處理函數
            uploaded_audios = await _upload_media_files(audio_input, 'audio')
            for uploaded_audio in uploaded_audios:
                current_parts.append(uploaded_audio)
            logger.info("音訊已添加到對話內容中")
        except Exception as e:
            logger.error(f"音訊處理失敗: {str(e)}")
            current_parts[0] = {"text": f"{inst}\n\n注意: 音訊處理發生錯誤，無法分析音訊內容"}
        
    elif image_input:
        current_parts.append({"text": inst})
        try:
            # 使用統一的多媒體處理函數
            uploaded_images = await _upload_media_files(image_input, 'image')
            for uploaded_image in uploaded_images:
                current_parts.append(uploaded_image)
            logger.info("圖片已添加到對話內容中")
        except Exception as e:
            logger.error(f"圖片處理失敗，使用降級方案: {str(e)}")
            # 降級：使用 inlineData 格式
            if isinstance(image_input, list):
                for img in image_input:
                    current_parts.append({
                        "inlineData": {
                            "mimeType": "image/jpeg",
                            "data": image_to_base64(img)
                        }
                    })
            else:
                current_parts.append({
                    "inlineData": {
                        "mimeType": "image/jpeg",
                        "data": image_to_base64(image_input)
                    }
                })
    else:
        # 純文字輸入
        current_parts.append({"text": inst})
    
    # 添加當前用戶輸入
    contents.append({
        "role": "user",
        "parts": current_parts
    })
    
    return contents

async def generate_response_with_cache(inst: str,
                                       system_prompt: str,
                                       response_schema: Optional[Type[BaseModel]] = None,
                                       dialogue_history=None,
                                       image_input=None,
                                       audio_input=None,
                                       video_input=None,
                                       pdf_input=None,
                                       use_cache=True,
                                       cache_ttl="3600s"):
    """帶快取功能的 Gemini API 回應生成器
    
    主要功能:
    1. 智慧快取系統指令和常用上下文
    2. 自動降級到傳統模式
    3. 支援多媒體輸入
    4. 流式回應處理
    
    Args:
        inst: 用戶輸入訊息
        system_prompt: 系統提示詞
        dialogue_history: 多輪對話歷史列表
        image_input: 圖片輸入
        audio_input: 音頻輸入
        video_input: 視頻輸入
        pdf_input: PDF 檔案輸入（URL 或本地路徑）
        use_cache: 是否使用快取（預設啟用）
        cache_ttl: 快取存留時間（預設1小時）
        response_schema: 用於結構化輸出的 Pydantic 模型。如果提供，將返回 JSON 物件。
    Returns:
        tuple: 返回值的格式會根據 response_schema 是否提供而變化
            - 若 response_schema is None: (None, async_generator) 用於流式文字回應
            - 若 response_schema is not None: (None, parsed_pydantic_object) 包含已解析的 Pydantic 物件
    """
    try:
        # 獲取快取管理器
        cache_mgr = get_cache_manager()
        
        # 處理多媒體檔案和建構內容
        contents = []
        media_files = []
        
        # 按優先級處理多媒體（PDF > 影片 > 音訊 > 圖片）
        if pdf_input:
            try:
                uploaded_pdfs = await _upload_media_files(pdf_input, 'pdf')
                media_files.extend(uploaded_pdfs)
                contents.append(inst)
                contents.extend(uploaded_pdfs)
                logger.info("PDF 上傳成功，使用官方 Files API")
            except Exception as e:
                logger.error(f"PDF 上傳失敗，降級處理: {str(e)}")
                contents = await _build_conversation_contents(inst, dialogue_history, image_input, audio_input, video_input, pdf_input)
        
        elif video_input:
            try:
                uploaded_videos = await _upload_media_files(video_input, 'video')
                media_files.extend(uploaded_videos)
                contents.append(inst)
                contents.extend(uploaded_videos)
                logger.info("影片上傳成功，使用官方 Files API")
            except Exception as e:
                logger.error(f"影片上傳失敗，降級處理: {str(e)}")
                contents = await _build_conversation_contents(inst, dialogue_history, image_input, audio_input, video_input, pdf_input)
        
        elif audio_input:
            try:
                uploaded_audios = await _upload_media_files(audio_input, 'audio')
                media_files.extend(uploaded_audios)
                contents.append("請分析這個音訊檔案: " + inst)
                contents.extend(uploaded_audios)
                logger.info("音訊上傳成功，使用官方 Files API")
            except Exception as e:
                logger.error(f"音訊上傳失敗，降級處理: {str(e)}")
                contents.append(f"{inst}\n\n注意: 音訊處理發生錯誤，無法分析音訊內容")
        
        elif image_input:
            try:
                uploaded_images = await _upload_media_files(image_input, 'image')
                media_files.extend(uploaded_images)
                contents.append(inst)
                contents.extend(uploaded_images)
                logger.info("圖片上傳成功，使用官方 Files API")
            except Exception as e:
                logger.error(f"圖片上傳失敗，降級處理: {str(e)}")
                contents = await _build_conversation_contents(inst, dialogue_history, image_input, audio_input, video_input, pdf_input)
        
        # 純文字輸入
        else:
            if dialogue_history:
                contents = await _build_conversation_contents(inst, dialogue_history, image_input, audio_input, video_input, pdf_input)
            else:
                contents.append(inst)
        
        generation_config_args = {}
        
        if response_schema:
            is_streaming = False
            # 根據官方最新用法，啟用 JSON 模式
            generation_config_args["response_mime_type"] = "application/json"
            generation_config_args["response_schema"] = response_schema
            logger.info(f"啟用結構化輸出 (JSON mode)，Schema: {response_schema.__name__}")
        else:
            is_streaming = True
            # 保持原有的流式文字輸出設定
            generation_config_args["tools"] = [google_search_tool]
            generation_config_args["response_modalities"] = ["TEXT"]
            
        # 嘗試使用快取
        cache = None
        if use_cache and cache_mgr:
            try:
                # 檢查是否有現有快取
                cache = cache_mgr.find_cache_by_system_instruction(system_prompt)
                
                # 如果沒有現有快取，創建新的
                if cache is None:
                    # 對於系統指令快取，我們只快取系統指令本身
                    cache_contents = media_files if media_files else []
                    cache = cache_mgr.create_cache(
                        model=model_id,
                        system_instruction=system_prompt,
                        contents=cache_contents,
                        ttl=cache_ttl,
                        display_name=f'discord_bot_system_{int(time.time())}'
                    )
                
                if cache:
                    config=types.GenerateContentConfig(
                                cached_content=cache.name, 
                                **generation_config_args
                            )
                    if response_schema:
                        # 如果有結構化輸出，使用快取生成結構化回應
                        logger.info("使用快取模式生成結構化回應")
                        response_object = cache_mgr.generate_with_cache(
                            model=model_id,
                            contents=contents,
                            config=config
                        )
                    else:
                        logger.info("使用快取模式生成回應")
                        # 使用快取生成流式回應
                        response_object = cache_mgr.generate_stream_with_cache(
                            model=model_id,
                            contents=contents,
                            config=config
                        )
                else:
                    logger.warning("快取創建失敗，使用傳統模式")
                    use_cache = False
                    
            except Exception as cache_error:
                logger.warning(f"快取操作失敗，降級到傳統模式: {str(cache_error)}")
                use_cache = False
        
        # 如果沒有使用快取，則使用傳統模式
        if not use_cache or cache is None:
            logger.info("使用傳統模式生成回應")
            config = GenerateContentConfig(system_instruction=system_prompt, **generation_config_args)
            if is_streaming:
                response_object = client.models.generate_content_stream(
                    model=model_id,
                    contents=contents,
                    config=config
                )
            else:
                response_object = client.models.generate_content(
                    model=model_id,
                    contents=contents,
                    config=config
                )
        if is_streaming:
            async def async_generator():
                try:
                    accumulated_text = ""
                    chunk_count = 0
                    
                    try:
                        for chunk in response_object:
                            chunk_count += 1
                            if chunk and hasattr(chunk, 'text') and chunk.text:
                                chunk_text = chunk.text.strip()
                                if chunk_text:
                                    accumulated_text += chunk_text
                                    yield chunk_text
                                    await asyncio.sleep(0.01)
                            elif chunk is None:
                                break
                    except StopIteration:
                        pass
                    except Exception as stream_error:
                        error_message = str(stream_error)
                        
                        if "Response not read" in error_message or "400 Bad Request" in error_message:
                            if accumulated_text:
                                yield accumulated_text
                                return
                            else:
                                # 降級到非流式調用
                                try:
                                    if cache and use_cache:
                                        fallback_response = cache_mgr.generate_with_cache(
                                            model='models/gemini-2.0-flash',
                                            cache=cache,
                                            contents=contents,
                                            tools=[google_search_tool],
                                            response_modalities=["TEXT"]
                                        )
                                    else:
                                        fallback_config = GenerateContentConfig(
                                            system_instruction=system_prompt,
                                            tools=[google_search_tool],
                                            response_modalities=["TEXT"],
                                        )
                                        
                                        fallback_response = client.models.generate_content(
                                            model=model_id,
                                            contents=contents,
                                            config=fallback_config
                                        )
                                    
                                    if fallback_response and fallback_response.text:
                                        yield fallback_response.text
                                        return
                                    else:
                                        raise GeminiError(f"Gemini API 流式和非流式回應都失敗: {error_message}")
                                        
                                except Exception as fallback_error:
                                    raise GeminiError(f"Gemini API 降級處理失敗: {fallback_error}")
                        
                        elif "RESOURCE_PROJECT_INVALID" in error_message:
                            raise GeminiError(f"Gemini API 項目設定錯誤: {error_message}")
                        elif "PERMISSION_DENIED" in error_message:
                            raise GeminiError(f"Gemini API 權限錯誤: {error_message}")
                        elif "QUOTA_EXCEEDED" in error_message:
                            raise GeminiError(f"Gemini API 配額超限: {error_message}")
                        else:
                            if accumulated_text:
                                yield accumulated_text
                                return
                            else:
                                raise GeminiError(f"Gemini API 錯誤: {error_message}")
                    
                    if not accumulated_text:
                        raise GeminiError("Gemini API 沒有生成任何回應內容")
                        
                except Exception as e:
                    raise GeminiError(f"Gemini API 生成過程錯誤: {str(e)}")
            # 返回異步生成器用於流式回應
            return None, async_generator()
        else:
            # 處理結構化 JSON 回應
            logger.info(f"收到結構化回應: {response_object.text[:500]}...")
            # 根據官方最新 SDK，解析後的 Pydantic 物件可直接獲取
            try:
                # `response.candidates[0].content.parts[0].json` 會自動使用 pydantic 進行解析
                parsed_data = response_object.parsed
                return None, parsed_data
            except (AttributeError, IndexError) as e:
                raise GeminiError(f"無法從 API 回應中提取 JSON 物件: {e}\n原始回應: {response_object.text}")
    except Exception as e:
        raise GeminiError(f"Gemini API 初始化錯誤: {str(e)}")
            
async def generate_response(inst, system_prompt, dialogue_history=None, image_input=None, audio_input=None, video_input=None, pdf_input=None):
    """根據 Gemini API 官方最佳實踐生成回應。
    
    主要改進:
    1. 使用 system_instruction 參數而非將系統提示詞混合到用戶訊息中
    2. 採用官方推薦的 client.files.upload() 處理多媒體檔案
    3. 使用簡化的 contents 格式，符合官方範例
    4. 遵循 Google Code Style Guide
    5. 支援 PDF 檔案處理
    
    Args:
        inst: 用戶輸入訊息
        system_prompt: 系統提示詞（將使用 system_instruction 參數）
        dialogue_history: 多輪對話歷史列表
        image_input: 圖片輸入（支援單張或多張圖片）
        audio_input: 音頻輸入
        video_input: 視頻輸入
        pdf_input: PDF 檔案輸入（URL 或本地路徑）
        
    Returns:
        tuple: (None, async_generator) 用於流式回應
    """
    try:
        # 處理多媒體檔案和建構內容
        contents = []
        
        # 統一處理多媒體輸入
        media_files = []
        
        # 按優先級處理多媒體（PDF > 影片 > 音訊 > 圖片）
        if pdf_input:
            try:
                uploaded_pdfs = await _upload_media_files(pdf_input, 'pdf')
                media_files.extend(uploaded_pdfs)
                contents.append(inst)
                contents.extend(uploaded_pdfs)
                logger.info("PDF 上傳成功，使用官方 Files API")
            except Exception as e:
                logger.error(f"PDF 上傳失敗，降級處理: {str(e)}")
                # 降級到結構化內容格式
                contents = await _build_conversation_contents(inst, dialogue_history, image_input, audio_input, video_input, pdf_input)
        
        elif video_input:
            try:
                uploaded_videos = await _upload_media_files(video_input, 'video')
                media_files.extend(uploaded_videos)
                contents.append(inst)
                contents.extend(uploaded_videos)
                logger.info("影片上傳成功，使用官方 Files API")
            except Exception as e:
                logger.error(f"影片上傳失敗，降級處理: {str(e)}")
                # 降級到結構化內容格式
                contents = await _build_conversation_contents(inst, dialogue_history, image_input, audio_input, video_input, pdf_input)
        
        elif audio_input:
            try:
                uploaded_audios = await _upload_media_files(audio_input, 'audio')
                media_files.extend(uploaded_audios)
                contents.append("請分析這個音訊檔案: " + inst)
                contents.extend(uploaded_audios)
                logger.info("音訊上傳成功，使用官方 Files API")
            except Exception as e:
                logger.error(f"音訊上傳失敗，降級處理: {str(e)}")
                contents.append(f"{inst}\n\n注意: 音訊處理發生錯誤，無法分析音訊內容")
        
        elif image_input:
            try:
                uploaded_images = await _upload_media_files(image_input, 'image')
                media_files.extend(uploaded_images)
                contents.append(inst)
                contents.extend(uploaded_images)
                logger.info("圖片上傳成功，使用官方 Files API")
            except Exception as e:
                logger.error(f"圖片上傳失敗，降級處理: {str(e)}")
                # 降級到結構化內容格式
                contents = await _build_conversation_contents(inst, dialogue_history, image_input, audio_input, video_input, pdf_input)
        
        # 純文字輸入
        else:
            # 如果有對話歷史，需要使用結構化格式
            if dialogue_history:
                contents = await _build_conversation_contents(inst, dialogue_history, image_input, audio_input, video_input, pdf_input)
            else:
                contents.append(inst)
        
        # 建構生成配置
        config = GenerateContentConfig(
            system_instruction=system_prompt,
            tools=[google_search_tool],
            response_modalities=["TEXT"],
        )

        response_stream = client.models.generate_content_stream(
            model=model_id,
            contents=contents,
            config=config
        )
        
        async def async_generator():
            try:
                # 使用正確的同步迭代方式處理 Gemini 回應流
                accumulated_text = ""
                chunk_count = 0
                
                try:
                    for chunk in response_stream:
                        chunk_count += 1
                        if chunk and hasattr(chunk, 'text') and chunk.text:
                            chunk_text = chunk.text.strip()
                            if chunk_text:
                                accumulated_text += chunk_text
                                yield chunk_text
                                await asyncio.sleep(0.01)  # 小幅延遲避免過快輸出
                        elif chunk is None:
                            break
                except StopIteration:
                    # 正常迭代結束
                    pass
                except Exception as stream_error:
                    error_message = str(stream_error)
                    
                    # 檢查特定錯誤類型
                    if "Response not read" in error_message or "400 Bad Request" in error_message:
                        # 嘗試獲取已累積的文字作為降級方案
                        if accumulated_text:
                            yield accumulated_text
                            return
                        else:
                            # 如果沒有累積文字，嘗試非流式呼叫
                            try:
                                # 重新建立配置進行非流式調用
                                from google.genai.types import GenerateContentConfig
                                fallback_config = GenerateContentConfig(
                                    system_instruction=system_prompt,
                                    tools=[google_search_tool],
                                    response_modalities=["TEXT"],
                                )
                                
                                fallback_response = client.models.generate_content(
                                    model=model_id,
                                    contents=contents,
                                    config=fallback_config,
                                    stream=False  # 非流式
                                )
                                
                                if fallback_response and fallback_response.text:
                                    yield fallback_response.text
                                    return
                                else:
                                    raise GeminiError(f"Gemini API 流式和非流式回應都失敗: {error_message}")
                                    
                            except Exception as fallback_error:
                                raise GeminiError(f"Gemini API 降級處理失敗: {fallback_error}")
                    
                    elif "RESOURCE_PROJECT_INVALID" in error_message:
                        raise GeminiError(f"Gemini API 項目設定錯誤: {error_message}")
                    elif "PERMISSION_DENIED" in error_message:
                        raise GeminiError(f"Gemini API 權限錯誤: {error_message}")
                    elif "QUOTA_EXCEEDED" in error_message:
                        raise GeminiError(f"Gemini API 配額超限: {error_message}")
                    else:
                        # 對於其他錯誤，如果有累積文字就返回
                        if accumulated_text:
                            yield accumulated_text
                            return
                        else:
                            raise GeminiError(f"Gemini API 錯誤: {error_message}")
                
                # 確保至少有一些輸出
                if not accumulated_text:
                    raise GeminiError("Gemini API 沒有生成任何回應內容")
                    
            except Exception as e:
                if isinstance(e, GeminiError):
                    raise
                raise GeminiError(f"Gemini API 生成過程錯誤: {str(e)}")

        # 返回異步生成器
        return None, async_generator()
    except Exception as e:
        raise GeminiError(f"Gemini API 初始化錯誤: {str(e)}")

