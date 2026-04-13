import datetime
from sqlalchemy import create_engine, select, update
from sqlalchemy.engine import Row
from sqlalchemy.orm import Session
from .tables import *

URI = "sqlite:///./data/eatdatabase.sqlite"

class DB:
    def __init__(self) -> None:
        self.engine = create_engine(URI, echo=False, future=True)
        Base.metadata.create_all(self.engine)

    def getKeywords(self) -> list: 
        getCommand = select(Keywords.keyword)
        # print(getCommand)

        with Session(self.engine) as session:
            result = session.execute(getCommand)
            keywords_list = result.all()
            
        return keywords_list

    def checkKeyword(self, keyword:String):
        getCommand = select(Keywords).where(Keywords.keyword == keyword)

        with Session(self.engine) as session:
            result = session.execute(getCommand)
            result_list = result.all()
        
        return result_list

    
    def storeKeyword(self, keyword: str) -> None:
        keyword_data = Keywords(keyword=keyword)

        with Session(self.engine) as session:
            session.add(keyword_data)
            session.commit()

    def storeSearchRecord(self, discord_id:str, title:str, keyword:str, map_rate:str, tag:str, map_address:str) -> int:
        searchRecord = SearchRecord(discord_id=discord_id, title=title, keyword=keyword, map_rate=map_rate, tag=tag, address=map_address, self_rate=0.5)

        with Session(self.engine) as session:
            session.add(searchRecord)
            session.commit()
            return searchRecord.id

    def getSearchRecoreds(self, discord_id:str) -> list: 
        getCommand = select(SearchRecord).where(SearchRecord.discord_id == discord_id)

        with Session(self.engine) as session:
            searchRecords = session.execute(getCommand)
            searchRecords_all = searchRecords.all()

        return searchRecords_all

    def updateRecordRate(self, id:int, new_rate: float) -> bool:
        with Session(self.engine) as session:
            # print(f"Debug: record: {record}")
            record:SearchRecord = session.get(SearchRecord, id)
            
            # print(f"Debug: record: {record}")

            if record == None:
                return False 

            record.self_rate = new_rate

            session.commit()

            return True

    def getRecentRecords(self, discord_id: str, days: int = 7) -> list:
        """取得最近 N 天內的搜尋記錄，用於避免重複推薦"""
        cutoff = datetime.datetime.now() - datetime.timedelta(days=days)
        getCommand = select(SearchRecord).where(
            SearchRecord.discord_id == discord_id,
            SearchRecord.date >= cutoff
        )
        with Session(self.engine) as session:
            result = session.execute(getCommand)
            return result.all()

    def getLikedRecords(self, discord_id: str) -> list:
        """取得 self_rate >= 1 的記錄（用戶喜歡的）"""
        getCommand = select(SearchRecord).where(
            SearchRecord.discord_id == discord_id,
            SearchRecord.self_rate >= 1
        )
        with Session(self.engine) as session:
            result = session.execute(getCommand)
            return result.all()

    def getDislikedRecords(self, discord_id: str) -> list:
        """取得 self_rate <= -1 的記錄（用戶不喜歡的）"""
        getCommand = select(SearchRecord).where(
            SearchRecord.discord_id == discord_id,
            SearchRecord.self_rate <= -1
        )
        with Session(self.engine) as session:
            result = session.execute(getCommand)
            return result.all()
