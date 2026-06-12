/**
 * Playwright webServer wrapper.
 *
 * Guarantees a clean test environment on every suite run:
 *  1. Tears down any stale containers from a previous (possibly killed) run
 *  2. Deletes ./test-db so the backend re-seeds a fresh database
 *     (fresh-start test asserts the default $10,000 cash balance)
 *  3. Starts the app via docker compose
 */
const { rmSync } = require('fs');
const { spawn, spawnSync } = require('child_process');
const path = require('path');

const cwd = __dirname;
const composeArgs = ['compose', '-f', 'docker-compose.test.yml'];

// 1. Tear down stale containers from previous runs
spawnSync('docker', [...composeArgs, 'down', '--remove-orphans'], { cwd, stdio: 'inherit' });

// 2. Reset the test database for a deterministic fresh start
try {
  rmSync(path.join(cwd, 'test-db'), { recursive: true, force: true });
} catch (err) {
  console.warn('Warning: could not remove test-db:', err.message);
}

// 3. Start the app (image should already be built; --build keeps it current)
const child = spawn('docker', [...composeArgs, 'up', '--build'], { cwd, stdio: 'inherit' });
child.on('exit', code => process.exit(code ?? 0));
