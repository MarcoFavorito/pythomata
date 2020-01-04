# -*- coding: utf-8 -*-
"""
An implementation of a symbolic automaton.

For further details, see:
- Applications of Symbolic Finite Automata
  https://www.microsoft.com/en-us/research/wp-content/uploads/2016/02/ciaa13.pdf
- Symbolic Automata Constraint Solving
  https://link.springer.com/chapter/10.1007%2F978-3-642-16242-8_45
- Rex: Symbolic Regular Expression Explorer
  https://www.microsoft.com/en-us/research/wp-content/uploads/2010/04/rex-ICST.pdf
"""
import operator
from typing import Set, Dict, Union, Any, Optional, FrozenSet, Tuple

import graphviz
import sympy
from sympy import Symbol, simplify, satisfiable, And, Not, Or
from sympy.logic.boolalg import BooleanFunction, BooleanTrue, BooleanFalse
from sympy.parsing.sympy_parser import parse_expr

from pythomata.core import FiniteAutomaton, SymbolType
from pythomata.utils import iter_powerset

PropInt = Dict[Union[str, Symbol], bool]


class SymbolicAutomaton(FiniteAutomaton[int, PropInt]):
    """A symbolic automaton."""

    def __init__(self):
        """Initialize a Symbolic automaton."""
        self._initial_states = set()
        self._states = set()
        self._final_states = set()  # type: Set[int]
        self._state_counter = 0

        self._transition_function = {}  # type: Dict[int, Dict[int, BooleanFunction]]

    @property
    def states(self) -> Set[int]:
        """Get the states."""
        return self._states

    @property
    def final_states(self) -> Set[int]:
        """Get the final states."""
        return self._final_states

    @property
    def initial_states(self) -> Set[int]:
        """Get the initial states."""
        return self._initial_states

    def get_successors(self, state: int, symbol: PropInt) -> Set[int]:
        """Get the successor states.."""
        if state not in self.states:
            raise ValueError("State not in set of states.")
        if not self._is_valid_symbol(symbol):
            raise ValueError("Symbol {} is not valid.".format(symbol))
        successors = set()
        transition_iterator = self._transition_function.get(state, {}).items()
        for successor, guard in transition_iterator:
            subexpr = guard.subs(symbol)
            subexpr = subexpr.replace(sympy.Symbol, BooleanFalse)
            if subexpr == True:  # noqa: E712
                successors.add(successor)
        return successors

    def create_state(self) -> int:
        """Create a new state."""
        new_state = self._state_counter
        self.states.add(new_state)
        self._state_counter += 1
        return new_state

    def remove_state(self, state: int) -> None:
        """Remove a state."""
        if state not in self.states:
            raise ValueError("State {} not found.".format(state))

        self._transition_function.pop(state, None)
        for s in self._transition_function:
            self._transition_function[s].pop(state, None)

    def set_final_state(self, state: int, is_final: bool) -> None:
        """Set a state to be final."""
        if state not in self.states:
            raise ValueError("State {} not found.".format(state))
        if is_final:
            self.final_states.add(state)
        else:
            try:
                self.final_states.remove(state)
            except KeyError:
                pass

    def set_initial_state(self, state: int, is_initial: bool) -> None:
        """Set a state to be an initial state."""
        if state not in self.states:
            raise ValueError("State {} not found.".format(state))
        if is_initial:
            self.initial_states.add(state)
        else:
            try:
                self.initial_states.remove(state)
            except KeyError:
                pass

    def add_transition(self, state1: int, guard: Union[BooleanFunction, str], state2: int) -> None:
        """
        Add a transition.

        :param state1: the start state of the transition.
        :param guard: the guard of the transition.
                      it can be either a sympy.logic.boolalg.BooleanFunction object
                      or a string that can be parsed with sympy.parsing.sympy_parser.parse_expr.
        :param state2:
        :return:
        """
        assert state1 in self.states
        assert state2 in self.states
        if isinstance(guard, str):
            guard = simplify(parse_expr(guard))
        other_guard = self._transition_function.get(state1, {}).get(state2, None)
        if other_guard is None:
            self._transition_function.setdefault(state1, {})[state2] = guard
        else:
            # take the OR of the two guards.
            self._transition_function[state1][state2] = simplify(other_guard | guard)

    def _is_valid_symbol(self, symbol: Any) -> bool:
        """Return true if the given symbol is valid, false otherwise."""
        try:
            assert isinstance(symbol, dict)
            assert all(isinstance(k, str) for k in symbol.keys())
            assert all(isinstance(v, bool) for v in symbol.values())
        except AssertionError:
            return False
        return True

    def complete(self) -> 'SymbolicAutomaton':
        """Complete the automaton."""
        states = set(self.states)
        initial_states = self.initial_states
        final_states = self.final_states
        transitions = set()
        sink_state = None
        for source in states:
            transitions_from_source = self._transition_function.get(source, {})
            transitions.update(set(map(lambda x: (source, x[1], x[0]), transitions_from_source.items())))
            guards = transitions_from_source.values()
            guards_negation = simplify(Not(Or(*guards)))
            if satisfiable(guards_negation) is not False:
                sink_state = len(states) if sink_state is None else sink_state
                transitions.add((source, guards_negation, sink_state))

        if sink_state is not None:
            states.add(sink_state)
            transitions.add((sink_state, BooleanTrue(), sink_state))
        return SymbolicAutomaton._from_transitions(states, initial_states, final_states, transitions)

    def determinize(self) -> 'SymbolicAutomaton':
        """Do determinize."""
        frozen_initial_states = frozenset(self.initial_states)  # type: FrozenSet[int]
        stack = [frozen_initial_states]
        visited = {frozen_initial_states}
        final_macro_states = {frozen_initial_states} if frozen_initial_states.intersection(
            self.final_states) != set() else set()  # type: Set[FrozenSet[int]]
        moves = set()

        # given an iterable of transitions (i.e. triples (source, guard, destination),
        # get the guard
        def getguard(x):
            return map(operator.itemgetter(1), x)

        # given ... (as before)
        # get the target
        def gettarget(x):
            return map(operator.itemgetter(2), x)

        while len(stack) > 0:
            macro_source = stack.pop()
            transitions = set([(source, guard, dest)
                               for source in macro_source
                               for dest, guard in self._transition_function.get(source, {}).items()])
            for transitions_subset in map(frozenset, iter_powerset(transitions)):
                if len(transitions_subset) == 0:
                    continue
                transitions_subset_negated = transitions.difference(transitions_subset)
                phi_positive = And(*getguard(transitions_subset))
                phi_negative = And(*map(Not, getguard(transitions_subset_negated)))
                phi = phi_positive & phi_negative
                if sympy.satisfiable(phi) is not False:
                    macro_dest = frozenset(gettarget(transitions_subset))  # type: FrozenSet[int]
                    moves.add((macro_source, phi, macro_dest))
                    if macro_dest not in visited:
                        visited.add(macro_dest)
                        stack.append(macro_dest)
                        if macro_dest.intersection(self.final_states) != set():
                            final_macro_states.add(macro_dest)

        return self._from_transitions(visited, {frozen_initial_states}, set(final_macro_states), moves)

    def minimize(self) -> FiniteAutomaton[int, PropInt]:
        """Minimize."""

    @classmethod
    def _from_transitions(cls, states: Set[Any],
                          initial_states: Set[Any],
                          final_states: Set[Any],
                          transitions: Set[Tuple[Any, SymbolType, Any]]):
        automaton = SymbolicAutomaton()
        state_to_indices = {}
        indices_to_state = {}

        for s in states:
            new_index = automaton.create_state()
            automaton.set_initial_state(new_index, s in initial_states)
            automaton.set_final_state(new_index, s in final_states)
            state_to_indices[s] = new_index
            indices_to_state[new_index] = s

        for (source, guard, destination) in transitions:
            source_index = state_to_indices[source]
            dest_index = state_to_indices[destination]
            automaton.add_transition(source_index, guard, dest_index)

        return automaton

    def to_graphviz(self, title: Optional[str] = None) -> graphviz.Digraph:
        """Convert to graphviz.Digraph object."""
        g = graphviz.Digraph(format="svg")
        g.node("fake", style="invisible")
        for state in self.states:
            if state in self.initial_states:
                if state in self.final_states:
                    g.node(str(state), root="true", shape="doublecircle")
                else:
                    g.node(str(state), root="true")
            elif state in self.final_states:
                g.node(str(state), shape="doublecircle")
            else:
                g.node(str(state))

        for i in self.initial_states:
            g.edge("fake", str(i), style="bold")
        for start in self._transition_function:
            for end, guard in self._transition_function[start].items():
                g.edge(str(start), str(end), label=str(guard))

        if title is not None:
            g.attr(label=title)
            g.attr(fontsize="20")

        return g
