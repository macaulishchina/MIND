export function createUiActionRunner({
  state,
  setStatus,
  syncActionAvailability,
  applyButtonDisabledState,
  delay,
}) {
  function measureBusyButtonWidth(button, label) {
    const computed = window.getComputedStyle(button);
    const probe = document.createElement("span");
    const rootFontSize = Number.parseFloat(
      window.getComputedStyle(document.documentElement).fontSize,
    ) || 16;
    const gap = Number.parseFloat(computed.columnGap || computed.gap || "0");
    const padding =
      (Number.parseFloat(computed.paddingLeft) || 0)
      + (Number.parseFloat(computed.paddingRight) || 0)
      + (Number.parseFloat(computed.borderLeftWidth) || 0)
      + (Number.parseFloat(computed.borderRightWidth) || 0);

    probe.textContent = label;
    probe.style.position = "absolute";
    probe.style.visibility = "hidden";
    probe.style.whiteSpace = "nowrap";
    probe.style.font = computed.font;
    probe.style.fontWeight = computed.fontWeight;
    probe.style.letterSpacing = computed.letterSpacing;
    document.body.append(probe);
    const labelWidth = probe.getBoundingClientRect().width;
    probe.remove();

    return Math.ceil(labelWidth + padding + (rootFontSize * 0.85) + gap + 2);
  }

  function setButtonBusy(button, busyLabel) {
    if (!button) {
      return () => {};
    }

    const defaultLabel = button.dataset.defaultLabel || button.textContent.trim();
    const originalWidth = button.getBoundingClientRect().width;
    const busyWidth = measureBusyButtonWidth(button, busyLabel);
    button.dataset.defaultLabel = defaultLabel;
    button.dataset.busy = "true";
    button.classList.add("is-busy");
    applyButtonDisabledState(button);
    button.setAttribute("aria-busy", "true");
    button.textContent = busyLabel;
    button.style.minWidth = `${Math.ceil(Math.max(originalWidth, busyWidth))}px`;

    return () => {
      delete button.dataset.busy;
      button.classList.remove("is-busy");
      button.removeAttribute("aria-busy");
      button.textContent = defaultLabel;
      button.style.minWidth = "";
      applyButtonDisabledState(button);
    };
  }

  async function runUiAction(
    actionKey,
    {
      button = null,
      busyLabel = "处理中",
      minBusyMs = 0,
      work,
      readyMessage,
    },
  ) {
    if (state.busyActions.has(actionKey)) {
      return null;
    }

    state.busyActions.add(actionKey);
    const restoreButton = setButtonBusy(button, busyLabel);
    const startedAt = Date.now();

    try {
      setStatus(state.apiKey ? "正在处理中..." : "当前还没有连接。");
      const result = await work();
      await delay(Math.max(0, minBusyMs - (Date.now() - startedAt)));
      setStatus(readyMessage || (state.apiKey ? "可以继续操作。" : "当前还没有连接。"));
      return result;
    } catch (error) {
      await delay(Math.max(0, minBusyMs - (Date.now() - startedAt)));
      setStatus(error instanceof Error ? error.message : "页面暂时没有完成这次操作，请稍后重试。");
      return null;
    } finally {
      restoreButton();
      state.busyActions.delete(actionKey);
      syncActionAvailability();
    }
  }

  function bindClickAction(
    button,
    actionKey,
    {
      before = null,
      work,
      busyLabel,
      minBusyMs,
      readyMessage,
    },
  ) {
    button.addEventListener("click", () => {
      if (typeof before === "function") {
        before();
      }
      void runUiAction(actionKey, {
        button,
        busyLabel,
        minBusyMs,
        readyMessage,
        work,
      });
    });
  }

  function bindFormAction(
    form,
    actionKey,
    {
      button,
      before = null,
      work,
      busyLabel,
      minBusyMs,
      readyMessage,
    },
  ) {
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      const submitter = event.submitter instanceof HTMLButtonElement ? event.submitter : button;
      if ((submitter || button)?.disabled) {
        return;
      }
      if (typeof before === "function") {
        before();
      }
      void runUiAction(actionKey, {
        button: submitter || button,
        busyLabel,
        minBusyMs,
        readyMessage,
        work,
      });
    });
  }

  return {
    bindClickAction,
    bindFormAction,
    runUiAction,
    setButtonBusy,
  };
}
