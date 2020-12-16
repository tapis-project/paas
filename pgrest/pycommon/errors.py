class BaseTapisError(Exception):
    """
    Base Tapis error class. All Error types should descend from this class.
    """
    def __init__(self, msg=None, code=400):
        """
        Create a new TapisError object.
        :param msg: (str) A helpful string
        :param code: (int) The HTTP return code that should be returned
        """
        self.msg = msg
        self.code = code
