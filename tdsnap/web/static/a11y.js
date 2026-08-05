/* Keyboard behavior shared by the app's radio-style button groups.
 *
 * Every `role="radiogroup"` gets one tab stop and arrow-key navigation, which
 * is what a screen-reader or switch user expects. This matters more here than
 * in most apps: the people configuring AAC devices often navigate this way
 * themselves.
 */

function wireRadioGroups(root = document) {
  root.querySelectorAll('[role="radiogroup"]').forEach((group) => {
    const selected = group.querySelector('[role="radio"][aria-checked="true"]');
    group.querySelectorAll('[role="radio"]').forEach((radio) => {
      radio.tabIndex = radio === selected ? 0 : -1;
    });
    group.addEventListener("keydown", (event) => {
      if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End"].includes(event.key)) {
        return;
      }
      const radios = [...group.querySelectorAll('[role="radio"]')].filter(
        (radio) => !radio.disabled
      );
      if (!radios.length) return;
      event.preventDefault();
      const current = Math.max(0, radios.indexOf(document.activeElement));
      let next = current;
      if (event.key === "Home") next = 0;
      else if (event.key === "End") next = radios.length - 1;
      else if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
        next = (current - 1 + radios.length) % radios.length;
      } else {
        next = (current + 1) % radios.length;
      }
      radios[next].click();
      radios[next].focus();
    });
  });
}

export { wireRadioGroups };
