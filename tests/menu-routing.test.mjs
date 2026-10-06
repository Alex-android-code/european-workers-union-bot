import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const source = readFileSync(new URL('../bot.js', import.meta.url), 'utf8');
const handlerStart = source.indexOf('async function handle(msg)');
const handlerEnd = source.indexOf('async function setup()');
assert.ok(handlerStart >= 0 && handlerEnd > handlerStart, 'Telegram handler is present');
const handlerSource = source.slice(handlerStart, handlerEnd);

const L = {
  uk: {
    candidate: '👷 Шукаю роботу',
    employer: '🏢 Шукаю працівників',
    legal: '📄 Легалізація і документи',
    about: 'ℹ️ Про EWU',
    contact: '📞 Зв’язатися з координатором',
    menu: 'Головне меню',
    welcome: 'Welcome',
    aboutText: 'About EWU',
  },
};

const flows = {
  candidate: { q: { uk: ['Candidate question 1'] } },
  employer: { q: { uk: ['Employer question 1'] } },
  legal: { q: { uk: ['Legal question 1'] } },
};

function buildHandler(initialMode) {
  const transitions = [];
  const sends = [];
  const flowCalls = [];
  const deps = {
    L,
    flows,
    LANGS: {},
    setSetting: async () => {},
    saveMsg: async () => {},
    start: async () => {},
    session: async () => ({ lang: 'uk', mode: initialMode, step: 2, data: {} }),
    setSession: async (...args) => transitions.push(args),
    send: async (...args) => sends.push(args),
    langKeyboard: () => [],
    menuKeyboard: () => [],
    handleFlow: async (...args) => flowCalls.push(args),
    pool: { query: async () => {} },
    uuid: () => 'test-id',
    aiChat: async () => null,
  };
  const bindings = Object.keys(deps).map((name) => 'const ' + name + ' = deps.' + name + ';').join('\n');
  const handle = new Function('deps', bindings + '\n' + handlerSource + '\nreturn handle;')(deps);
  return { handle, transitions, sends, flowCalls };
}

const cases = [
  ['candidate to employer', 'candidate', L.uk.employer, 'employer'],
  ['employer to candidate', 'employer', L.uk.candidate, 'candidate'],
  ['candidate to legalization', 'candidate', L.uk.legal, 'legal'],
  ['candidate to about', 'candidate', L.uk.about, 'menu'],
  ['employer to contact', 'employer', L.uk.contact, 'contact'],
  ['contact to employer', 'contact', L.uk.employer, 'employer'],
  ['candidate to main menu', 'candidate', L.uk.menu, 'menu'],
];

for (const [name, fromMode, text, expectedMode] of cases) {
  test('EWU navigation: ' + name, async () => {
    const { handle, transitions, flowCalls } = buildHandler(fromMode);
    await handle({ from: { id: 100 }, chat: { id: 100, type: 'private' }, text });
    assert.equal(transitions.length, 1, 'Navigation should update the session exactly once');
    assert.equal(transitions[0][2], expectedMode, 'Navigation should switch to the expected form');
    assert.equal(flowCalls.length, 0, 'Menu buttons must not be treated as answers to an active form');
  });
}

test('A normal candidate answer still continues the questionnaire', async () => {
  const { handle, transitions, flowCalls } = buildHandler('candidate');
  await handle({ from: { id: 100 }, chat: { id: 100, type: 'private' }, text: 'Example Candidate' });
  assert.equal(transitions.length, 0);
  assert.equal(flowCalls.length, 1);
});
