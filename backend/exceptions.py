class GamearrError(Exception):
    ''' base exception rule for subsystem propagation '''

    def __init__(self, message: str, title_id: str = None):
        self.message = message
        self.title_id = title_id
        super().__init__(self.message)


class StorageError(GamearrError):
    '''
    OPERATOR: Raised when NAS I/O contraints fail.
    Traps cross-device links, stale SMB handles, and LXC VLAN permission drops.
    '''
    pass


class MetadataError(GamearrError):
    '''
    OPERATOR: Raised during IGDB timeout or OAuth invalidation.
    '''
    pass


class ExtractionError(GamearrError):
    '''
    OPERATOR: raised during pk2zip decryption failures or zRIF payload rejection
    '''
    pass
