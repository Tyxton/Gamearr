class GamearrError(Exception):
    ''' base exception rule '''

    def __init__(self, message: str, title_id: str = None):
        self.message = message
        self.title_id = title_id
        super().__init__(self.message)


class StorageError(GamearrError):
    ''' when disk io fails '''
    pass


class MetadataError(GamearrError):
    ''' failure in IGDB or 3rd party API '''
    pass


class ExtractionError(GamearrError):
    ''' pkg2zip decryption error '''
    pass
