// Vinext calls process.exit(0) immediately after its HTTP prerender server closes.
// On Windows/Node 24 this can abort while libuv is still closing the socket:
// https://github.com/nodejs/node/issues/58091
// Give pending close callbacks one brief turn to finish. Nonzero exits retain
// their original behavior; no build error or validation result is overridden.
if (process.platform === 'win32') {
  const exit = process.exit.bind(process);
  process.exit = (code) => {
    if (code !== 0) return exit(code);
    setTimeout(() => exit(process.exitCode || 0), 200);
  };
}
process.argv = [process.execPath, 'vinext', 'build', ...process.argv.slice(2)];
await import('../node_modules/vinext/dist/cli.js');
