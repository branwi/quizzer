"use strict";
document.addEventListener("DOMContentLoaded", () => {
  const editor = document.querySelector("[data-question-editor]");
  if (editor) {
    const adapt = () => editor.querySelectorAll("[data-type-section]").forEach(section => {
      const active = section.dataset.typeSection === editor.querySelector("[data-type-picker]").value;
      section.hidden = !active;
      section.querySelectorAll("input, textarea").forEach(field => field.disabled = !active);
    });
    editor.querySelector("[data-type-picker]").addEventListener("change", adapt);
    adapt();
  }
  const selectionForm = document.querySelector("[data-selection-form]");
  if (selectionForm) {
    const selection = new Map(JSON.parse(selectionForm.dataset.initial || "[]").map(item => [String(item.id), item]));
    const labels = new Map(Object.entries(JSON.parse(selectionForm.dataset.labels || "{}")));
    const serialize = () => { selectionForm.elements.selection.value = JSON.stringify([...selection.values()]); };
    const repaint = () => {
      selectionForm.querySelectorAll("[data-pick]").forEach(box => {
        labels.set(box.value, box.dataset.label);
        if (!box.disabled) box.checked = selection.has(box.value);
      });
      selectionForm.querySelectorAll("[data-points]").forEach(input => {
        const item = selection.get(input.dataset.points);
        input.disabled = !item;
        if (item) input.value = item.points;
      });
      selectionForm.querySelectorAll("[data-selection-count]").forEach(node => node.textContent = selection.size);
      selectionForm.querySelectorAll("[data-needs-selection]").forEach(button => button.disabled = selection.size === 0);
      const summary = selectionForm.querySelector("[data-selection-summary]");
      if (summary) {
        summary.replaceChildren();
        for (const [id, item] of selection) {
          const chip = document.createElement("div"); chip.className = "selected-chip";
          const label = document.createElement("span"); label.textContent = labels.get(id) || "Selected question unavailable";
          const points = document.createElement("input"); points.type = "number"; points.min = "1"; points.max = "1000000"; points.required = true; points.value = item.points; points.dataset.summaryPoints = id; points.setAttribute("aria-label", "Points for " + label.textContent);
          const remove = document.createElement("button"); remove.type = "button"; remove.textContent = "×"; remove.setAttribute("aria-label", "Remove " + label.textContent); remove.addEventListener("click", () => { selection.delete(id); repaint(); });
          chip.append(label, points, document.createTextNode("pt"), remove); summary.append(chip);
        }
      }
      serialize();
    };
    selectionForm.addEventListener("change", event => {
      const field = event.target;
      if (field.matches("[data-pick]")) {
        if (field.checked) selection.set(field.value, {id: Number(field.value), points: 1});
        else selection.delete(field.value);
        repaint();
      } else if (field.matches("[data-points], [data-summary-points]")) {
        const id = field.dataset.points || field.dataset.summaryPoints;
        if (selection.has(id) && field.checkValidity()) { selection.get(id).points = Number(field.value); repaint(); }
      }
    });
    selectionForm.addEventListener("submit", () => {
      const input = document.activeElement;
      if (input && input.matches("[data-points], [data-summary-points]")) {
        const id = input.dataset.points || input.dataset.summaryPoints;
        if (!input.disabled && selection.has(id)) selection.get(id).points = Number(input.value);
      }
      serialize();
    });
    document.body.addEventListener("htmx:afterSwap", repaint);
    repaint();
  }
  document.querySelectorAll("form[data-confirm]").forEach(form => form.addEventListener("submit", event => {
    if (!window.confirm(form.dataset.confirm)) event.preventDefault();
  }));
  document.querySelectorAll("time[datetime]").forEach(node => {
    const value = new Date(node.dateTime);
    if (!Number.isNaN(value.valueOf())) node.title = value.toLocaleString();
  });
});
