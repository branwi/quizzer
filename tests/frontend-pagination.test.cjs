// Exercise the real page handlers with a small DOM and a paginated API stub.
// Run with: node --test tests/frontend-pagination.test.cjs
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

class Element {
  constructor(tag = "div") {
    this.tag = tag;
    this.children = [];
    this.listeners = {};
    this.attributes = {};
    this.dataset = {};
    this.value = "";
    this.disabled = false;
    this.hidden = false;
    this._text = "";
    const classes = new Set();
    this.classList = { toggle(name, enabled) {
      if (enabled) classes.add(name); else classes.delete(name);
    } };
  }
  set textContent(text) { this._text = String(text); this.children = []; }
  get textContent() { return this._text + this.children.map((child) => child.textContent).join(""); }
  get options() { return this.children; }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this._text = ""; this.children = children; }
  setAttribute(key, value) { this.attributes[key] = value; }
  addEventListener(name, callback) { this.listeners[name] = callback; }
  querySelector(tag) {
    for (const child of this.children) {
      if (child.tag === tag) return child;
      const found = child.querySelector(tag);
      if (found) return found;
    }
    return null;
  }
  reset() {}
  scrollIntoView() {}
  focus() {}
  dispatch(name, extra = {}) {
    return this.listeners[name]?.({ preventDefault() {}, submitter: new Element("button"), ...extra });
  }
}

async function flush() {
  for (let n = 0; n < 5; n++) await new Promise(setImmediate);
}

async function harness() {
  const root = path.join(__dirname, "..");
  const html = fs.readFileSync(path.join(root, "frontend/index.html"), "utf8");
  const elements = new Map([...html.matchAll(/id="([^"]+)"/g)].map((match) => [match[1], new Element()]));
  const questions = Array.from({ length: 45 }, (_, n) => ({
    id: n + 1, text: `Question ${n + 1}: $x+1$`, topic: n < 23 ? "Number Theory" : "Combinatorics",
    correct_answer: [String(n + 1)], explanation: "$x=1$.",
  }));
  const calls = [];
  const mathCalls = [];
  let saved = null;
  let failNext = false;
  const response = (data, status = 200, total = 0, page = 1) => ({
    status, ok: status < 400, json: async () => data,
    headers: { get: (key) => String(key === "X-Total-Count" ? total : page) },
  });
  const fetch = async (url, options = {}) => {
    calls.push({ url, ...options });
    const parsed = new URL(url, "http://localhost");
    if (parsed.pathname === "/api/me") return response({ detail: "Not authenticated" }, 401);
    if (parsed.pathname === "/api/students") return response([{ id: 2, first_name: "Sam", grade: "6" }]);
    if (parsed.pathname === "/api/bank/questions/topics") return response([...new Set(questions.map((q) => q.topic))].sort());
    if (parsed.pathname.endsWith("/check")) {
      const question = questions.find((q) => q.id === Number(parsed.pathname.split("/").at(-2)));
      const submitted = JSON.parse(options.body).response;
      return response({ is_correct: question.correct_answer.includes(submitted), correct_answer: question.correct_answer, explanation: question.explanation });
    }
    if (options.method === "POST" || (options.method === "PUT" && parsed.pathname.startsWith("/api/questions/"))) {
      const body = JSON.parse(options.body);
      assert.equal(Object.hasOwn(body, "type"), false);
      assert.equal(Object.hasOwn(body, "choices"), false);
      if (options.method === "POST") {
        const question = { id: 46, ...body };
        questions.push(question);
        return response(question, 201);
      }
      const question = questions.find((q) => q.id === Number(parsed.pathname.split("/").at(-1)));
      Object.assign(question, body);
      return response(question);
    }
    if (parsed.pathname.startsWith("/api/assignments")) {
      if (options.method === "PUT") saved = JSON.parse(options.body).question_ids;
      return response(questions.filter((q) => [1, 42].includes(q.id)));
    }
    if (failNext) { failNext = false; throw new Error("Offline"); }
    const query = parsed.searchParams;
    assert.equal(query.has("q"), false, "Bank requests must not send the removed text search parameter");
    const filtered = questions.filter((q) => !query.get("topic") || q.topic === query.get("topic"));
    const size = Number(query.get("page_size"));
    assert.equal(size, 20, "Bank requests must specify a bounded page size");
    const page = Math.min(Number(query.get("page")), Math.max(1, Math.ceil(filtered.length / size)));
    return response(filtered.slice((page - 1) * size, page * size), 200, filtered.length, page);
  };
  const context = vm.createContext({
    document: { getElementById: (id) => {
      assert.ok(elements.has(id), `Missing HTML element: ${id}`);
      return elements.get(id);
    }, createElement: (tag) => new Element(tag) },
    window: { renderMathInElement: (node) => mathCalls.push(node), confirm: () => true },
    Option: class extends Element {
      constructor(text, value) { super("option"); this.textContent = text; this.value = String(value); }
    },
    fetch, URLSearchParams, console,
  });
  vm.runInContext(fs.readFileSync(path.join(root, "frontend/app.js"), "utf8"), context);
  await flush();
  return {
    el: (id) => elements.get(id), run: (code) => vm.runInContext(code, context), calls, mathCalls,
    saved: () => saved, fail: () => { failNext = true; }, clearBank: () => { questions.length = 0; },
  };
}

test("the short-answer editor creates and edits accepted answer lists", async () => {
  const h = await harness();
  await h.run('openRoom({id:1, role:"teacher", first_name:"brian", grade:"12"})');
  h.el("question-topic").value = "Math";
  h.el("question-text").value = "What is 2 + 2?";
  h.el("accepted-answers").value = " 4 \n four \n";
  h.el("question-explanation").value = "Two plus two equals four.";
  h.el("question-form").dispatch("submit");
  await flush();
  const created = h.calls.find((call) => call.url === "/api/questions" && call.method === "POST");
  assert.deepEqual(JSON.parse(created.body), {
    text: "What is 2 + 2?", topic: "Math", correct_answer: ["4", "four"],
    explanation: "Two plus two equals four.",
  });
  await h.run("editQuestion(state.questions.find(question => question.id === 46))");
  assert.equal(h.el("accepted-answers").value, "4\nfour");
  h.el("accepted-answers").value = "FOUR";
  h.el("question-form").dispatch("submit");
  await flush();
  const edited = h.calls.find((call) => call.url === "/api/questions/46" && call.method === "PUT");
  assert.deepEqual(JSON.parse(edited.body).correct_answer, ["FOUR"]);
});

test("student cards submit text and display accepted answers as feedback", async () => {
  const h = await harness();
  await h.run('openRoom({id:2, role:"student", first_name:"Sam", grade:"6"})');
  const card = h.el("student-problems").children[0];
  const form = card.querySelector("form");
  const input = form.querySelector("input");
  assert.equal(input.type, "text");
  input.value = "wrong";
  form.dispatch("submit");
  await flush();
  const call = h.calls.find((item) => item.url === "/api/bank/questions/1/check");
  assert.deepEqual(JSON.parse(call.body), { response: "wrong" });
  assert.match(form.textContent, /Accepted answer: 1/);
});

test("teacher renders one page, keeps selections across pages, and saves off-page IDs", async () => {
  const h = await harness();
  await h.run('openRoom({id:1, role:"teacher", first_name:"brian", grade:"12"})');
  h.el("student-select").value = "2";
  await h.run("loadSelection()");
  assert.equal(h.el("teacher-problems").children.length, 20);
  const select = (id, checked) => {
    const card = h.el("teacher-problems").children.find((item) => item.children[0].id === `select-question-${id}`);
    card.children[0].checked = checked;
    card.children[0].dispatch("change");
  };
  select(2, true);
  h.el("teacher-pagination-bottom").children[2].dispatch("click");
  await flush();
  assert.equal(h.run("state.teacherPage"), 2);
  await h.run("loadTeacherPage(3)");
  assert.equal(h.el("teacher-problems").children.length, 5);
  assert.equal(h.el("teacher-problems").children[1].children[0].checked, true);
  select(42, false);
  select(41, true);
  assert.equal(h.el("teacher-pagination-top").children[2].disabled, true);
  await h.run("loadTeacherPage(1)");
  assert.equal(h.el("teacher-problems").children[1].children[0].checked, true);
  assert.equal(h.el("teacher-pagination-top").children[0].disabled, true);
  h.el("assignment-form").dispatch("submit");
  await flush();
  assert.deepEqual(h.saved().sort((a, b) => a - b), [1, 2, 41]);
  assert.equal(h.el("selection-count").textContent, "3 selected");
});

test("student paging renders at most 20 cards and handles an empty bank", async () => {
  const h = await harness();
  await h.run('openRoom({id:2, role:"student", first_name:"Sam", grade:"6"})');
  assert.equal(h.el("student-pagination-top").hidden, true);
  h.el("bank-tab").dispatch("click");
  await flush();
  assert.equal(h.el("student-problems").children.length, 20);
  const before = h.mathCalls.length;
  h.el("student-pagination-top").children[2].dispatch("click");
  await flush();
  assert.equal(h.run("state.bankPage"), 2);
  assert.equal(h.mathCalls.length - before, 20, "Only visible cards should render math");
  await h.run("loadStudent(3)");
  assert.equal(h.el("student-problems").children.length, 5);
  assert.equal(h.el("student-pagination-bottom").children[2].disabled, true);
  h.clearBank();
  await h.run("loadStudent(1)");
  assert.equal(h.run("state.bankPage"), 1);
  assert.equal(h.el("problem-count").textContent, "0 problems");
  assert.equal(h.el("student-pagination-top").hidden, true);
  assert.match(h.el("student-problems").textContent, /No problems found/);
});

test("a failed teacher page request preserves choices and re-enables navigation", async () => {
  const h = await harness();
  await h.run('openRoom({id:1, role:"teacher", first_name:"brian", grade:"12"})');
  h.el("student-select").value = "2";
  await h.run("loadSelection()");
  h.fail();
  await assert.rejects(h.run("loadTeacherPage(2)"), /Offline/);
  assert.equal(h.run("state.teacherPage"), 1);
  assert.equal(h.el("teacher-problems").children.length, 20);
  assert.equal(h.el("teacher-pagination-top").children[2].disabled, false);
  assert.equal(h.el("save-assignments-button").disabled, false);
  assert.equal(h.run("state.selected.has(42)"), true);
});

test("topic choices include the whole bank and stay applied across pages", async () => {
  const h = await harness();
  await h.run('openRoom({id:2, role:"student", first_name:"Sam", grade:"6"})');
  h.el("bank-tab").dispatch("click");
  await flush();
  assert.deepEqual(h.el("topic-filter").options.map((option) => option.textContent), ["All topics", "Combinatorics", "Number Theory"]);
  await h.run("loadStudent(3)");
  h.el("topic-filter").value = "Number Theory";
  h.el("topic-filter").dispatch("change");
  await flush();
  assert.equal(h.run("state.bankPage"), 1);
  assert.equal(h.el("problem-count").textContent, "23 problems");
  assert.equal(h.el("student-problems").children.length, 20);
  h.el("student-pagination-top").children[2].dispatch("click");
  await flush();
  assert.equal(h.el("student-problems").children.length, 3);
  assert.equal(h.el("topic-filter").value, "Number Theory");
  h.el("topic-filter").value = "";
  h.el("topic-filter").dispatch("change");
  await flush();
  assert.equal(h.run("state.bankPage"), 1);
  assert.equal(h.el("problem-count").textContent, "45 problems");
});
