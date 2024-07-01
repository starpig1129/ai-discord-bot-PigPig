import logging
import os
from datetime import datetime

class TimedRotatingFileHandler(logging.Handler):
    def __init__(self, server_name):
        super().__init__()
        self.server_name = server_name
        self.current_date = datetime.now().strftime('%Y%m%d')
        self.current_hour = datetime.now().strftime('%H')
        self._create_new_folder()
        self._open_new_file()

    def _create_new_folder(self):
        log_directory = f'logs/{self.server_name}/{self.current_date}'
        if not os.path.exists(log_directory):
            os.makedirs(log_directory)
        self.log_directory = log_directory

    def _open_new_file(self):
        log_filename = os.path.join(self.log_directory, f'bot_log_{self.current_hour}.log')
        self.stream = open(log_filename, 'a', encoding='utf-8')

    def emit(self, record):
        current_date = datetime.now().strftime('%Y%m%d')
        current_hour = datetime.now().strftime('%H')
        if current_date != self.current_date or current_hour != self.current_hour:
            self.stream.close()
            self.current_date = current_date
            self.current_hour = current_hour
            self._create_new_folder()
            self._open_new_file()
        msg = self.format(record)
        self.stream.write(msg + '\n')
        self.stream.flush()

    def close(self):
        self.stream.close()
        super().close()

def setup_logger(server_name):
    logger = logging.getLogger(server_name)
    logger.setLevel(logging.INFO)
    handler = TimedRotatingFileHandler(server_name)
    formatter = logging.Formatter('%(asctime)s %(levelname)s:%(message)s')
    handler.setFormatter(formatter)
    # 移除所有默認的處理程序
    if logger.hasHandlers():
        logger.handlers.clear()
    logger.addHandler(handler)
    return logger
