import wavelink
import random
import asyncio

class CustomQueue(wavelink.Queue):
    MAX_QUEUE_SIZE = 50

    def __init__(self, bot):
        super().__init__()
        self.bot = bot
        self._shuffle_mode = False

    @property
    def shuffle_mode(self) -> bool:
        return self._shuffle_mode

    @shuffle_mode.setter
    def shuffle_mode(self, value: bool):
        self._shuffle_mode = value

    def put_wait(self, item: wavelink.Track):
        added_by_user = 'requester' in item.extras and item.extras['requester'].id != self.bot.user.id

        if self.count >= self.MAX_QUEUE_SIZE:
            if added_by_user:
                # Try to remove a bot-added song to make space
                for i in range(len(self) - 1, -1, -1):
                    track = self[i]
                    if 'requester' in track.extras and track.extras['requester'].id == self.bot.user.id:
                        self._queue.remove(track)
                        break
                else:
                    # No bot-added song to remove
                    return
            else:
                # Song is added by bot and queue is full
                return

        if added_by_user:
            # Insert user-added song before the first bot-added song
            insert_index = -1
            for i, track in enumerate(self):
                if 'requester' in track.extras and track.extras['requester'].id == self.bot.user.id:
                    insert_index = i
                    break

            if insert_index != -1:
                self._queue.insert(insert_index, item)
            else:
                self._queue.append(item)
        else:
            # Bot-added songs are always added to the end
            self._queue.append(item)

    def get(self):
        if not self:
            return None

        if self.shuffle_mode:
            return self._queue.pop(random.randrange(len(self)))

        return super().get()
