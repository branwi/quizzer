// This page uses the same JSON API as /docs. Login is remembered by the cookie.
const $ = (id) => document.getElementById(id);
const PAGE_SIZE = 20;
const state = {
  user: null, page: "assigned", questions: [], students: [], selected: new Set(), editing: null,
  bankPage: 1, bankTotal: 0, bankTopic: "", teacherPage: 1, teacherTotal: 0,
  teacherLoading: false, selectionLoading: false,
};
let selectionRequest = 0;
let studentRequest = 0;
let teacherRequest = 0;
let rosterRequest = 0;

function element(tag, className = "", text = "") {
  const node = document.createElement(tag);
  node.className = className;
  node.textContent = text;
  return node;
}

function renderMath(node) {
  if (!window.renderMathInElement) return;
  window.renderMathInElement(node, {
    delimiters: [
      { left: "$$", right: "$$", display: true },
      { left: "$", right: "$", display: false },
      { left: "\\(", right: "\\)", display: false },
      { left: "\\[", right: "\\]", display: true },
    ],
    throwOnError: false,
    trust: false,
  });
}

function notice(message = "", error = false) {
  $("notice").textContent = message;
  $("notice").classList.toggle("error", error);
  $("notice").hidden = !message;
}

async function request(path, { method = "GET", body, paginated = false } = {}) {
  const response = await fetch(`/api${path}`, {
    method,
    credentials: "same-origin",
    headers: body === undefined ? {} : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = response.status === 204 ? null : await response.json().catch(() => null);
  if (!response.ok) {
    if (response.status === 401) showLogin();
    const detail = data?.detail;
    const message = Array.isArray(detail)
      ? detail.map((item) => `${item.loc.at(-1)}: ${item.msg}`).join("\n")
      : detail || "Something went wrong. Please try again.";
    const error = new Error(response.status === 401 ? "Please log in to continue." : message);
    error.status = response.status;
    throw error;
  }
  if (paginated) return {
    items: data,
    total: Number(response.headers.get("X-Total-Count")),
    page: Number(response.headers.get("X-Page")),
  };
  return data;
}

function renderPagination(prefix, page, total, onPage, pending = false) {
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  for (const position of ["top", "bottom"]) {
    const nav = $(`${prefix}-pagination-${position}`);
    nav.hidden = total <= PAGE_SIZE;
    const previous = element("button", "button secondary", "Previous");
    const next = element("button", "button secondary", "Next");
    previous.type = next.type = "button";
    previous.disabled = pending || page <= 1;
    next.disabled = pending || page >= pages;
    const first = total ? (page - 1) * PAGE_SIZE + 1 : 0;
    const last = Math.min(page * PAGE_SIZE, total);
    const status = element("span", "page-status", `${first}–${last} of ${total} · Page ${page} of ${pages}`);
    status.setAttribute("aria-live", "polite");
    for (const [button, target] of [[previous, page - 1], [next, page + 1]]) {
      button.addEventListener("click", () => {
        notice();
        onPage(target).catch((error) => notice(error.message, true));
      });
    }
    nav.replaceChildren(previous, status, next);
  }
}

function studentPagination(pending = false) {
  renderPagination("student", state.bankPage, state.page === "bank" ? state.bankTotal : 0,
    (page) => loadStudent(page, true), pending);
}

function teacherPagination() {
  renderPagination("teacher", state.teacherPage, state.teacherTotal,
    (page) => loadTeacherPage(page, true), state.teacherLoading);
}

async function busy(button, action) {
  button.disabled = true;
  try { await action(); }
  catch (error) { notice(error.message || "Could not connect. Please try again.", true); }
  finally { button.disabled = false; }
}

function showLogin() {
  state.user = null;
  state.questions = [];
  state.students = [];
  state.selected.clear();
  state.bankPage = state.teacherPage = 1;
  state.bankTotal = state.teacherTotal = 0;
  state.bankTopic = "";
  state.teacherLoading = state.selectionLoading = false;
  selectionRequest++;
  studentRequest++;
  teacherRequest++;
  rosterRequest++;
  $("loading").hidden = true;
  $("login-view").hidden = false;
  $("account").hidden = true;
  $("teacher-view").hidden = true;
  $("student-view").hidden = true;
  $("teacher-problems").replaceChildren();
  $("student-problems").replaceChildren();
  resetEditor();
}

async function openRoom(user) {
  state.user = user;
  state.bankPage = state.teacherPage = 1;
  state.bankTopic = "";
  notice();
  $("loading").hidden = true;
  $("login-view").hidden = true;
  $("account").hidden = false;
  $("profile-label").textContent = `${user.first_name} · Grade ${user.grade}`;
  $("teacher-view").hidden = user.role !== "teacher";
  $("student-view").hidden = user.role !== "student";
  if (user.role === "teacher") await loadTeacher();
  else {
    state.page = "assigned";
    $("topic-filter").value = "";
    await loadStudent();
  }
}

function empty(title, description) {
  const box = element("div", "empty-state");
  box.append(element("h3", "", title), element("p", "", description));
  return box;
}

function questionContent(question) {
  const content = element("div");
  const meta = element("div", "problem-meta");
  meta.append(element("span", "topic-badge", question.topic));
  content.append(meta, element("h3", "question-text", question.text));
  return content;
}

function answerText(answers) {
  return answers.join(" or ");
}

function studentCard(question) {
  const card = element("article", "problem-card");
  card.append(questionContent(question));
  const form = element("form", "answer-form");
  const textInput = element("input");
  textInput.type = "text";
  textInput.maxLength = 2000;
  textInput.required = true;
  textInput.placeholder = "Your answer";
  textInput.setAttribute("aria-label", `Your answer to ${question.text}`);
  form.append(textInput);
  const button = element("button", "button secondary", "Check answer");
  button.type = "submit";
  const feedback = element("div", "answer-feedback");
  feedback.hidden = true;
  feedback.setAttribute("role", "status");
  form.append(button, feedback);
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    busy(button, async () => {
      const response = textInput.value;
      const result = await request(`/bank/questions/${question.id}/check`, { method: "POST", body: { response } });
      feedback.replaceChildren(element("strong", "", result.is_correct ? "That’s right. Nice work!" : "Not quite. Here’s a little help."));
      if (!result.is_correct) feedback.append(element("p", "", `Accepted answer: ${answerText(result.correct_answer)}`));
      if (result.explanation) feedback.append(element("p", "", result.explanation));
      renderMath(feedback);
      feedback.classList.toggle("correct", result.is_correct);
      feedback.hidden = false;
    });
  });
  card.append(form);
  renderMath(card);
  return card;
}

async function loadStudent(bankPage = state.bankPage, scroll = false) {
  const version = ++studentRequest;
  const page = state.page;
  const userId = state.user?.id;
  const assigned = page === "assigned";
  $("assigned-tab").classList.toggle("active", assigned);
  $("bank-tab").classList.toggle("active", !assigned);
  $("assigned-tab").setAttribute("aria-pressed", String(assigned));
  $("bank-tab").setAttribute("aria-pressed", String(!assigned));
  $("bank-filters").hidden = assigned;
  $("student-problems").replaceChildren(element("p", "loading", "Finding your problems…"));
  const query = new URLSearchParams();
  if (state.bankTopic) query.set("topic", state.bankTopic);
  query.set("page", bankPage);
  query.set("page_size", PAGE_SIZE);
  studentPagination(true);
  $("student-problems").setAttribute("aria-busy", "true");
  try {
    const [result, topics] = await Promise.all([
      assigned ? request("/assignments").then((items) => ({ items }))
        : request(`/bank/questions?${query}`, { paginated: true }),
      assigned ? Promise.resolve(null) : request("/bank/questions/topics"),
    ]);
    if (version !== studentRequest || state.user?.id !== userId || state.page !== page) return;
    if (topics) {
      const selected = $("topic-filter").value;
      $("topic-filter").replaceChildren(new Option("All topics", ""), ...topics.map((topic) => new Option(topic, topic)));
      if (topics.includes(selected)) $("topic-filter").value = selected;
    }
    const questions = result.items;
    const total = assigned ? questions.length : result.total;
    if (!assigned) {
      state.bankPage = result.page;
      state.bankTotal = total;
    }
    $("problem-count").textContent = `${total} problem${total === 1 ? "" : "s"}`;
    if (assigned) $("assigned-count").textContent = questions.length;
    $("student-problems").replaceChildren(...questions.map(studentCard));
    if (!questions.length) $("student-problems").append(empty(
      assigned ? "A little breathing room." : "No problems found.",
      assigned ? "No problems assigned yet. Check back after your teacher adds some, or explore the problem bank." : "Choose another topic, or check back when new problems are added.",
    ));
    if (scroll) $("student-pagination-top").scrollIntoView({ block: "start" });
  } finally {
    if (version === studentRequest) {
      studentPagination();
      $("student-problems").setAttribute("aria-busy", "false");
    }
  }
}

async function loadTeacher() {
  const version = ++rosterRequest;
  const students = await request("/students");
  if (version !== rosterRequest || state.user?.role !== "teacher") return;
  state.students = students;
  const previous = $("student-select").value;
  $("student-select").replaceChildren(new Option(students.length ? "Select student" : "No students", ""));
  for (const student of students) $("student-select").append(new Option(`${student.first_name} · Grade ${student.grade}`, student.id));
  if (students.some((student) => String(student.id) === previous)) $("student-select").value = previous;
  await Promise.all([loadTeacherPage(), loadSelection()]);
}

async function loadTeacherPage(page = state.teacherPage, scroll = false) {
  const version = ++teacherRequest;
  state.teacherLoading = true;
  teacherPagination();
  updateSelectionCount();
  $("teacher-problems").setAttribute("aria-busy", "true");
  $("teacher-problems").replaceChildren(element("p", "loading", "Loading the problem bank…"));
  try {
    const result = await request(`/questions?page=${page}&page_size=${PAGE_SIZE}`, { paginated: true });
    if (version !== teacherRequest || state.user?.role !== "teacher") return;
    state.questions = result.items;
    state.teacherPage = result.page;
    state.teacherTotal = result.total;
    if (scroll) $("teacher-pagination-top").scrollIntoView({ block: "start" });
  } finally {
    if (version === teacherRequest && state.user?.role === "teacher") {
      state.teacherLoading = false;
      $("teacher-problems").setAttribute("aria-busy", "false");
      renderTeacherProblems();
      teacherPagination();
    }
  }
}

async function loadSelection() {
  const version = ++selectionRequest;
  const studentId = $("student-select").value;
  state.selectionLoading = true;
  state.selected.clear();
  if (!state.teacherLoading) renderTeacherProblems();
  updateSelectionCount();
  const current = studentId ? await request(`/assignments/${studentId}`) : [];
  if (version !== selectionRequest || state.user?.role !== "teacher") return;
  state.selected = new Set(current.map((question) => question.id));
  state.selectionLoading = false;
  if (!state.teacherLoading) renderTeacherProblems();
  updateSelectionCount();
}

function updateSelectionCount() {
  const student = state.students.find((item) => String(item.id) === $("student-select").value);
  $("selection-count").textContent = student ? `${state.selected.size} selected` : `${state.teacherTotal} in the bank`;
  $("save-assignments-button").disabled = !student || state.selectionLoading || state.teacherLoading;
}

function teacherCard(question) {
  const card = element("article", "problem-card teacher-card");
  card.classList.toggle("selected", state.selected.has(question.id));
  const checkbox = element("input");
  checkbox.type = "checkbox";
  checkbox.id = `select-question-${question.id}`;
  checkbox.checked = state.selected.has(question.id);
  checkbox.disabled = !$("student-select").value || state.selectionLoading;
  checkbox.setAttribute("aria-label", `Assign ${question.text}`);
  checkbox.addEventListener("change", () => {
    if (checkbox.checked) state.selected.add(question.id);
    else state.selected.delete(question.id);
    card.classList.toggle("selected", checkbox.checked);
    updateSelectionCount();
  });
  const content = questionContent(question);
  const heading = content.querySelector("h3");
  heading.replaceChildren();
  const label = element("label", "", question.text);
  label.htmlFor = checkbox.id;
  heading.append(label);
  const actions = element("div", "card-actions");
  const answer = element("details");
  answer.append(element("summary", "", "View answer"), element("p", "", `Answer: ${answerText(question.correct_answer)}`));
  if (question.explanation) answer.append(element("p", "", question.explanation));
  answer.addEventListener("toggle", () => {
    if (answer.open && !answer.dataset.mathRendered) {
      renderMath(answer);
      answer.dataset.mathRendered = "true";
    }
  });
  const buttons = element("div");
  const edit = element("button", "button subtle", "Edit");
  edit.type = "button";
  edit.addEventListener("click", () => editQuestion(question));
  const remove = element("button", "button subtle danger", "Delete");
  remove.type = "button";
  remove.addEventListener("click", () => {
    if (!window.confirm("Delete this problem and remove it from every student's assigned list?")) return;
    busy(remove, async () => {
      await request(`/questions/${question.id}`, { method: "DELETE" });
      state.selected.delete(question.id);
      if (state.editing?.id === question.id) resetEditor();
      await loadTeacherPage();
      notice("Problem deleted.");
    });
  });
  buttons.append(edit, remove);
  actions.append(answer, buttons);
  content.append(actions);
  card.append(checkbox, content);
  renderMath(heading);
  return card;
}

function renderTeacherProblems() {
  $("teacher-problems").replaceChildren(...state.questions.map(teacherCard));
  if (!state.questions.length) $("teacher-problems").append(empty("No problems.", ""));
  updateSelectionCount();
}

function resetEditor() {
  state.editing = null;
  $("question-form").reset();
  $("editor-title").textContent = "Add problem";
  $("save-question-button").textContent = "Add to bank";
  $("editor").open = false;
}

function editQuestion(question) {
  state.editing = question;
  $("question-topic").value = question.topic;
  $("question-text").value = question.text;
  $("question-explanation").value = question.explanation || "";
  $("accepted-answers").value = question.correct_answer.join("\n");
  $("editor-title").textContent = "Edit problem";
  $("save-question-button").textContent = "Save problem";
  $("editor").open = true;
  $("editor").scrollIntoView({ behavior: "smooth", block: "start" });
  $("question-text").focus({ preventScroll: true });
}

$("login-form").addEventListener("submit", (event) => {
  event.preventDefault();
  busy(event.submitter, async () => {
    const result = await request("/auth/login", { method: "POST", body: { first_name: $("first-name").value, grade: $("grade").value } });
    await openRoom(result.user);
  });
});
$("logout-button").addEventListener("click", () => busy($("logout-button"), async () => {
  await request("/auth/logout", { method: "POST" });
  notice();
  $("login-form").reset();
  showLogin();
}));
$("refresh-button").addEventListener("click", () => busy($("refresh-button"), async () => {
  notice();
  if (state.user?.role === "teacher") await loadTeacher();
  else await loadStudent();
}));
for (const page of ["assigned", "bank"]) $(`${page}-tab`).addEventListener("click", () => {
  state.page = page;
  notice();
  loadStudent().catch((error) => notice(error.message, true));
});
function filterByTopic() {
  state.bankTopic = $("topic-filter").value;
  return loadStudent(1);
}
$("topic-filter").addEventListener("change", () => busy($("topic-filter"), filterByTopic));
$("student-select").addEventListener("change", () => {
  notice();
  loadSelection().catch((error) => notice(error.message, true));
});
$("assignment-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const studentId = $("student-select").value;
  if (!studentId) return;
  busy($("save-assignments-button"), async () => {
    $("student-select").disabled = true;
    try {
      await request(`/assignments/${studentId}`, { method: "PUT", body: { question_ids: [...state.selected] } });
      notice("Assignments saved.");
    } finally { $("student-select").disabled = false; }
  });
});
$("add-problem-button").addEventListener("click", () => {
  resetEditor();
  $("editor").open = true;
  $("question-topic").focus();
});
$("cancel-edit-button").addEventListener("click", resetEditor);
$("question-form").addEventListener("submit", (event) => {
  event.preventDefault();
  busy($("save-question-button"), async () => {
    const body = {
      text: $("question-text").value,
      topic: $("question-topic").value,
      explanation: $("question-explanation").value.trim() || null,
      correct_answer: $("accepted-answers").value.split("\n").map((answer) => answer.trim()).filter(Boolean),
    };
    if (!body.correct_answer.length) throw new Error("Add at least one accepted answer.");
    const editing = state.editing;
    await request(editing ? `/questions/${editing.id}` : "/questions", { method: editing ? "PUT" : "POST", body });
    resetEditor();
    await loadTeacherPage(editing ? state.teacherPage : Math.floor(state.teacherTotal / PAGE_SIZE) + 1, true);
    notice(editing ? "Problem saved." : "Problem added.");
  });
});

async function start() {
  try { await openRoom(await request("/me")); }
  catch (error) {
    showLogin();
    if (error.status !== 401) notice("Could not load your room. Check your connection and refresh.", true);
  }
}
start();
