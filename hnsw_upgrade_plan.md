# Faiss 索引升級計畫：從 FlatL2 到 HNSW

## 1. 簡介

本文件旨在規劃將記憶體系統中使用的 Faiss 向量索引從目前的 `IndexFlatL2`（或其他暴力搜尋索引）升級為 `IndexHNSWFlat` (Hierarchical Navigable Small World)。此次升級的主要目標是大幅提升大規模向量搜尋的效能（速度）和品質（精度），同時保持系統的穩定性。

## 2. 現有實作分析

在 `cogs/memory/vector_manager.py` 的 `VectorIndex` 類別中：

*   **索引建立 (`_create_index`)**: 目前的實作主要使用 `faiss.IndexFlatL2`。雖然程式碼中已存在建立 `faiss.IndexHNSWFlat` 的分支，但其參數 `M` 被硬編碼為 32，缺乏彈性。
*   **訓練 (`_create_index`)**: 程式碼包含了對 `IVF` 類型索引的訓練邏輯，但 HNSW 索引在建立後不需要獨立的訓練步驟，可以直接新增向量。
*   **搜尋 (`search`)**: 目前的搜尋方法未提供設定 HNSW 特定參數（如 `efSearch`）的介面，這對搜尋效能至關重要。
*   **相容性**: 系統在載入索引時，沒有檢查其類型。若直接替換，舊有的 `IndexFlatL2` 索引檔案將無法被正確處理。

## 3. 升級步驟詳解

### 3.1. 索引建立修改 (`VectorIndex.__init__` & `VectorIndex._create_index`)

我們需要將 `faiss.IndexFlatL2(dimension)` 替換為 `faiss.IndexHNSWFlat(dimension, M)`，並使其可配置。

*   **修改內容**:
    1.  修改 `VectorIndex.__init__` 方法，增加一個 `hnsw_m: int = 64` 參數，允許外部傳入 `M` 值。
    2.  在 `_create_index` 方法中，使用此 `hnsw_m` 參數來建立 HNSW 索引：`index = faiss.IndexHNSWFlat(self.dimension, self.hnsw_m)`。

*   **`M` 參數說明**:
    *   `M` 代表 HNSW 圖中每個節點（向量）的鄰居數量。它是平衡搜尋效能和記憶體佔用的關鍵參數。
    *   較大的 `M` 值會建立更密集的圖，提升搜尋精度，但也會增加記憶體使用和索引建立時間。
    *   **建議預設值**: `M = 64`。這個值在多數應用場景中提供了良好的速度與精度平衡。可設定範圍通常在 16 到 256 之間。

### 3.2. 訓練與新增

HNSW 索引的一大優點是不需要像 `IVF` 索引一樣進行獨立的 `train` 步驟。向量可以直接被 `add` 到索引中，圖結構會動態建立。

*   **修改內容**:
    *   確保在 `_create_index` 方法中，當 `index_type` 為 `HNSW` 時，跳過訓練區塊。目前的程式碼邏輯 `if hasattr(index, 'is_trained') and not index.is_trained:` 已經可以正確處理此情況，無需修改。

### 3.3. 搜尋參數 (`VectorIndex.search`)

為了在搜尋時利用 HNSW 的優勢，我們必須設定 `hnsw.efSearch` 參數。

*   **修改內容**:
    1.  修改 `VectorIndex.search` 方法的簽章，增加一個可選參數 `ef_search: Optional[int] = None`。
    2.  在執行搜尋前，檢查索引是否為 HNSW 類型，並設定 `efSearch` 參數。

    **程式碼範例:**
    ```python
    # 在 VectorIndex.search 方法內部
    index = self.get_index()
    
    is_hnsw = False
    hnsw_index_obj = None

    if isinstance(index, faiss.IndexHNSW):
        is_hnsw = True
        hnsw_index_obj = index.hnsw
    elif hasattr(index, 'index') and isinstance(index.index, faiss.IndexHNSW): # GPU-wrapped index
        is_hnsw = True
        hnsw_index_obj = index.index.hnsw

    if is_hnsw and ef_search is not None:
        self.logger.debug(f"Setting HNSW efSearch to {ef_search}")
        hnsw_index_obj.efSearch = ef_search

    distances, faiss_ids = index.search(query_vector, k)
    ```

*   **`efSearch` 參數說明**:
    *   `efSearch` 控制搜尋期間探索的鄰居（節點）數量。它直接影響搜尋的精度和速度。
    *   `efSearch` 的值必須大於等於 `k`（欲回傳的結果數量）。
    *   較大的 `efSearch` 值會帶來更高的搜尋精度，但也會增加搜尋耗時。
    *   **建議值**:
        *   **預設值**: `efSearch = 128`。這是一個很好的起點。
        *   **動態調整**: 可以在 `VectorManager.search_similar` 方法中，根據不同的使用情境（例如，高精度需求的背景知識查詢 vs. 快速的即時對話查詢）傳入不同的 `efSearch` 值。

### 3.4. 向下相容性策略 (`VectorIndex.load`)

為了平滑過渡，系統需要能處理舊的 `IndexFlatL2` 索引檔案。我們建議採用**自動轉換**的方案。

*   **修改內容**:
    *   在 `VectorIndex.load` 方法中，載入 `index.faiss` 後，檢查其類型。

    **程式碼範例:**
    ```python
    # 在 VectorIndex.load 方法內部，成功載入 index 物件後
    
    if isinstance(self._index, faiss.IndexFlatL2):
        self.logger.warning(f"偵測到舊的 IndexFlatL2 格式索引，將觸發自動轉換...")
        
        try:
            if self._index.ntotal == 0:
                self.logger.warning("舊索引為空，無需轉換。")
            else:
                old_vectors = self._index.reconstruct_n(0, self._index.ntotal)
                
                self.logger.info(f"正在建立新的 HNSW 索引 (M={self.hnsw_m})...")
                new_hnsw_index = faiss.IndexHNSWFlat(self.dimension, self.hnsw_m)
                
                new_hnsw_index.add(old_vectors)
                
                self._index = new_hnsw_index
                self.index_type = "HNSW"
                self.logger.info("HNSW 索引轉換成功！")
                
                # 應搭配一個 'dirty' 標記機制，以確保下次會儲存新格式的檔案。
            
        except Exception as e:
            self.logger.error(f"自動轉換 HNSW 索引失敗: {e}。將繼續使用舊的 IndexFlatL2 索引。")

    ```

*   **方案優點**:
    *   **無縫升級**: 使用者無需手動干預，系統會自動完成升級。
    *   **效能提升**: 一旦轉換完成，該頻道的搜尋效能立即獲得提升。
    *   **漸進式部署**: 轉換只在索引被載入時觸發，不會造成系統啟動時的巨大負擔。

## 4. 總結與建議

本次升級將顯著改善記憶體系統的核心效能。建議的實施順序如下：

1.  **實作 `VectorIndex` 的修改**: 套用 3.1, 3.2, 3.3 節的程式碼變更。
2.  **實作向下相容性**: 在 `VectorIndex.load` 中加入 3.4 節的自動轉換邏輯。
3.  **調整 `VectorManager`**: 修改 `create_channel_index` 和 `search_similar` 方法，以傳遞和利用新的 `hnsw_m` 和 `ef_search` 參數。
4.  **測試**: 進行完整測試，包括：
    *   建立新的 HNSW 索引。
    *   搜尋功能是否正常，`efSearch` 是否生效。
    *   載入舊的 `IndexFlatL2` 索引時，自動轉換是否被觸發且成功。
    *   GPU 和 CPU 模式下的功能是否都正常。

完成以上步驟後，系統將能以更高效能的方式運作。