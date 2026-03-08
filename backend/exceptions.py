class GamearrError(Exception):
    ''' base exception rule '''

    def __init__(self, message: str, title_id: str = None):
        self.message = message
        self.title_id = title_id
        super().__init__(self.message)


class StorageError(GamearrError):
    pass


class MetadataError(GamearrError):
    pass


class ExtractionError(GamearrError):
    pass


class LogsError(GamearrError):
    pass
