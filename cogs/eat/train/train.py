
# inspire by https://github.com/pyliaorachel/resurrecting-the-dead-chinese
# import problem solve ref: https://blog.csdn.net/gcl916/article/details/121092665
import os
import sys
import numpy as np

import torch
import torch.nn.functional
from torch.autograd import Variable

import json
import pickle

from .data_loader import DataLoader
from .model import Net
sys.path.append(os.getcwd())
from ..db.db import DB
from addons.logging import get_logger

SAVE_URI = os.getcwd() + "/models/"

class Train():
    def __init__(self, db:DB, embedding_dim=128, hidden_dim=64, dropout=0.2, learn_rate=0.0001, epochs=50, save_interval=10, log_interval=3) -> None:
        self.db = db
        self.embedding_dim = embedding_dim
        self.hidden_dim = hidden_dim
        self.dropout = dropout
        self.learn_rate = learn_rate
        self.epochs = epochs
        self.save_interval = save_interval
        self.log_interval = log_interval
        self.logger = get_logger(server_id="Bot", source="eat.train")

    def genModel(self, discord_id:str):
        
        if os.path.exists(SAVE_URI) is False:
            os.mkdir(SAVE_URI)
        
        dataLoader = DataLoader(db=self.db)
        data = dataLoader.loadingData(discord_id=discord_id)
        cut_title_list, tag_list, keyword_list = dataLoader.procressData(data=data)

        voc_list = []
        for i in cut_title_list:
            voc_list.append(i)
        
        for i in tag_list:
            voc_list.append(i)
        
        for i in keyword_list:
            voc_list.append(i)
        
        tensor_data, dataX, voc_to_int, int_to_voc, vocabulary = dataLoader.transform(voc_list)
        model = Net(len(dataLoader.genVocabularyList(voc_list)), self.embedding_dim, self.hidden_dim, self.dropout)
        optimizer = torch.optim.Adam(model.parameters(), lr=self.learn_rate)

        for epoch in range(self.epochs):
            model.train()

            for batch_size, (voc_in, target) in enumerate(tensor_data):
                voc_in, target = Variable(voc_in), Variable(target)
                optimizer.zero_grad()

                output = model(voc_in)
                loss = torch.nn.functional.cross_entropy(output, target)
                loss.backward()
                optimizer.step()

                # Log training status
                if batch_size % self.log_interval == 0:
                    self.logger.info('Train epoch: {}\tLoss: {:.6f}'.format(epoch+1, loss.data))

            if (epoch + 1) % self.save_interval == 0:
                model.eval()
                torch.save(model.state_dict(), SAVE_URI + f"{discord_id}.model")

        model.eval()
        torch.save(model.state_dict(), SAVE_URI + f"{discord_id}.model")

        try:
            with open(SAVE_URI + f"{discord_id}.json", "w") as file:
                json.dump((dataX, voc_to_int, int_to_voc, list(vocabulary) if isinstance(vocabulary, set) else vocabulary), file)
        except TypeError:
            # Fallback if there are other un-serializable objects (though dataX is list of lists, and vocabulary is sorted list from data_loader)
            with open(SAVE_URI + f"{discord_id}.json", "w") as file:
                json.dump((dataX, voc_to_int, int_to_voc, list(vocabulary) if isinstance(vocabulary, set) else vocabulary), file, default=lambda o: o.tolist() if hasattr(o, 'tolist') else str(o))

        return (SAVE_URI + f"{discord_id}.model", SAVE_URI + f"{discord_id}.json")


    def predict(self, discord_id:str):
        if not os.path.exists(SAVE_URI + f"{discord_id}.model"):
            return None

        dataX, voc_to_int, int_to_voc, vocabulary = None, None, None, None

        if os.path.exists(SAVE_URI + f"{discord_id}.json"):
            with open(SAVE_URI + f"{discord_id}.json", "r") as file:
                dataX, voc_to_int, int_to_voc_raw, vocabulary = json.load(file)
                int_to_voc = {int(k): v for k, v in int_to_voc_raw.items()}
        elif os.path.exists(SAVE_URI + f"{discord_id}.pickle"):
            with open(SAVE_URI + f"{discord_id}.pickle", "rb") as file:
                dataX, voc_to_int, int_to_voc, vocabulary = pickle.load(file)

        if dataX is not None:
            dataLoader = DataLoader(db=self.db)
            model = Net(len(vocabulary), self.embedding_dim, self.hidden_dim, self.dropout)
            
            model.load_state_dict(torch.load(SAVE_URI + f"{discord_id}.model", weights_only=True))

            n_voc = len(dataX)

            voc = dataX[np.random.randint(0, n_voc - 1)]

            voc_in = np.array(voc)
            voc_in = voc_in.reshape(1, -1)

            voc_in = Variable(torch.LongTensor(voc_in))

            pred = model(voc_in)
            vec = torch.nn.functional.softmax(pred, dim=1).data[0].numpy()

            # Ensure proper casting and normalization to exactly sum to 1.0
            vec = np.array([float(v) for v in vec], dtype=np.float64)
            vec_sum = np.sum(vec)
            if vec_sum > 0:
                pred = vec / vec_sum
            else:
                pred = np.ones(len(vec)) / len(vec)

            voc_pred = np.random.choice(vocabulary, p=pred)

            # print(vocabulary)

            voc_index = voc_to_int[voc_pred]

            return voc_pred
        
        else:
            return None



# for testing
if __name__ == "__main__":
    db = DB()
    train = Train(db=db)

    print(train.genModel(discord_id="180713963510693888"))
    print(train.predict(discord_id="180713963510693888"))