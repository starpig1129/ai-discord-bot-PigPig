# inspire by https://github.com/pyliaorachel/resurrecting-the-dead-chinese

import os, sys
import jieba
import numpy as np
import torch

# import problem solve ref: https://blog.csdn.net/gcl916/article/details/121092665
sys.path.append(os.getcwd())

from ..db.db import DB

class DataLoader():
    def __init__(self, db:DB) -> None:
        self.db = db

    def loadingData(self, discord_id:str):
        return self.db.getSearchRecoreds(discord_id=discord_id)

    def procressData(self, data):
        cut_title_list = list()
        tag_list = list()
        keyword_list = list()
        self_rate_list = list()

        # 枚舉出來的物件會是 Table object，直接用 attribute 取得需要的資訊
        for i in data:

            # 關於喜好問題，目前我們應只要訓練出使用者確定喜歡的餐廳or關鍵字即可
            # 從資料篩出
            if i[0].self_rate >= 1:

                cut_title = jieba.lcut_for_search(i[0].title)

                #移除標題可能會有的符號，避免影響訓練結果
                for title_seq in cut_title:
                    if title_seq == "|" or title_seq == "-" or title_seq == "/" or title_seq == "｜" or title_seq == " " or title_seq == "（" or title_seq == "）" or title_seq == "【" or title_seq == "】":
                        cut_title.remove(title_seq)

                # 一次如果清理不乾淨：暴力解-清兩次 (?)
                for title_seq in cut_title:
                    if title_seq == "|" or title_seq == "-" or title_seq == "/" or title_seq == "｜" or title_seq == " " or title_seq == "（" or title_seq == "）" or title_seq == "【" or title_seq == "】":
                        cut_title.remove(title_seq)

                # 盡可能刪除只有一個字的狀況
                for title_seq in cut_title:
                    if len(title_seq) < 2:
                        cut_title.remove(title_seq)

                # 一次不夠就兩次（不太好的暴力解）
                for title_seq in cut_title:
                    if len(title_seq) < 2:
                        cut_title.remove(title_seq)

                cut_title_list.append(cut_title)
                tag_list.append(i[0].tag)
                keyword_list.append(i[0].keyword)
        
        return cut_title_list, tag_list, keyword_list

    def genVocabularyList(self, data):
        # 確保資料唯一性
        vocabulary = set()
        for i in data:
            for j in i:
                if len(j) > 1:
                    vocabulary.add(j)
        return sorted(list(vocabulary))

    def transform(self, data, voc_length=1, batch_size=5):
        # TODO: 想辦法轉換資料成 tensor
        
        # 確保資料唯一性
        vocabulary = self.genVocabularyList(data)

        voc_to_int = dict((v, i) for i, v in enumerate(vocabulary))
        int_to_voc = dict((i, v) for i, v in enumerate(vocabulary))

        n_voc = len(vocabulary)
        dataX = [] # N x voc_length
        dataY = [] # N x 1

        """
        嘗試做出input-target pair
        試著找出喜好關聯性

        例如說input為'晚餐'，target有可能會有'中國菜'
        """
        for i in range(0, n_voc - voc_length):
            voc_input = vocabulary[i:i+voc_length]
            voc_output = vocabulary[i+voc_length]
            dataX.append([voc_to_int[voc] for voc in voc_input])
            dataY.append(voc_to_int[voc_output])
        
        # mini-batch 做法：不足 batch size 的資料直接丟掉

        new_n_voc = len(dataY)
        new_n_voc = new_n_voc - new_n_voc % batch_size
        X = dataX[:new_n_voc]
        Y = dataY[:new_n_voc]

        # 每個 array 以 batch size 筆資料包成一組
        X = np.array(X)
        
        # by copilot
        #  FIXME IndexError: tuple index out of range
        if len(X.shape) < 2 or X.shape[1] < 2:
            voc_shape = 1
        else:
            _, voc_shape = X.shape    
        print(type(X),X,"batch_size",batch_size,"voc_shape",voc_shape)
        
        X = X.reshape(-1, batch_size, voc_shape) # 不太懂 numpy 只好照抄

        X = torch.LongTensor(X)

        Y = np.array(Y)
        Y = Y.reshape(-1, batch_size)

        Y = torch.LongTensor(Y)

        return list(zip(X, Y)), dataX, voc_to_int, int_to_voc, vocabulary


# For testing
if __name__ == "__main__":
    db = DB()
    dataLoader = DataLoader(db=db)
    
    data = dataLoader.loadingData(discord_id="180713963510693888")

    cut_title_list, tag_list, keyword_list = dataLoader.procressData(data=data)

    # print(cut_title_list)

    print(dataLoader.transform(cut_title_list))

    