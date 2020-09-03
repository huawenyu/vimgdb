class Pattern:
    __slots__ = ["rePatt", "hint", "sample", "actionCb", "nextState"]
    def __init__(self, rePatt, hint, sample, actionCb, nextState):
        self.rePatt = rePatt
        self.hint = hint
        self.sample = sample
        self.actionCb = actionCb
        self.nextState = nextState
