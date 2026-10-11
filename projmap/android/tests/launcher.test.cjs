// Testes das funções puras do lançador: node --test tests/
const test = require("node:test");
const assert = require("node:assert");
const { isPrivateHost, parseTarget, remoteUrl } = require("../www/launcher.js");

test("isPrivateHost aceita só a rede local", () => {
  for (const h of ["192.168.0.10", "10.0.2.2", "172.16.0.1", "172.31.255.255", "localhost", "127.0.0.1"]) {
    assert.ok(isPrivateHost(h), h);
  }
  for (const h of ["8.8.8.8", "172.32.0.1", "192.169.0.1", "example.com", "999.1.1.1", ""]) {
    assert.ok(!isPrivateHost(h), h);
  }
});

test("parseTarget lê a URL do QR", () => {
  assert.deepStrictEqual(parseTarget("http://192.168.1.12:8100/remote/#t=abc%2B1"),
    { host: "192.168.1.12", port: 8100, token: "abc+1" });
});

test("parseTarget aceita ip[:porta] e token digitado", () => {
  assert.deepStrictEqual(parseTarget("10.0.0.5", "tok"), { host: "10.0.0.5", port: 8100, token: "tok" });
  assert.deepStrictEqual(parseTarget("10.0.0.5:9000", ""), { host: "10.0.0.5", port: 9000, token: "" });
});

test("parseTarget recusa internet e lixo", () => {
  assert.throws(() => parseTarget("http://8.8.8.8/remote/"), /rede local/);
  assert.throws(() => parseTarget(""), /IP/);
});

test("remoteUrl monta o link com token no hash", () => {
  assert.strictEqual(remoteUrl({ host: "10.0.0.5", port: 8100, token: "a b" }), "http://10.0.0.5:8100/remote/#t=a%20b");
  assert.strictEqual(remoteUrl({ host: "10.0.0.5", port: 8100, token: "" }), "http://10.0.0.5:8100/remote/");
});
