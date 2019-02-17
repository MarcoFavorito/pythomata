# -*- coding: utf-8 -*-
from itertools import chain, combinations


LABEL_MAX_LENGTH = 15


def powerset(iterable):
    "powerset([1,2,3]) --> () (1,) (2,) (3,) (1,2) (1,3) (2,3) (1,2,3)"
    s = list(set(iterable))
    combs = chain.from_iterable(combinations(s, r) for r in range(len(s)+1))
    res = set(frozenset(x) for x in combs)
    # res = map(frozenset, combs)
    return res


class MacroState(frozenset):

    def __str__(self):
        if len(self)==0:
            return "{}"
        else:
            return super().__str__().replace("MacroState(", "")[:-1]

    def __repr__(self):
        return super().__repr__()
