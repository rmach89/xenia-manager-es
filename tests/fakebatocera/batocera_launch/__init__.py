class BatoceraException(Exception):
    pass

class Command:
    def __init__(self, args, env=None):
        self.args = list(args)
        self.env = dict(env or {})
