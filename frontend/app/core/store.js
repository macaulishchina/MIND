export function createStore(initialState) {
  const state = initialState;
  const listeners = new Set();

  function notify() {
    listeners.forEach((listener) => listener(state));
  }

  return {
    state,
    getState() {
      return state;
    },
    patchState(patch) {
      Object.assign(state, patch);
      notify();
    },
    replaceState(nextState) {
      Object.keys(state).forEach((key) => {
        delete state[key];
      });
      Object.assign(state, nextState);
      notify();
    },
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
  };
}
