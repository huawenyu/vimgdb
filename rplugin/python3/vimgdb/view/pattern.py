class Pattern:
    __slots__ = ["rePatts", "hint", "actionCb", "nextState", "update_model"]
    def __init__(self, rePatts, hint, actionCb, nextState):
        self.rePatts = rePatts
        self.hint = hint
        self.actionCb = actionCb
        self.nextState = nextState
        self.update_model = True
