/**
 * Global teardown: stop the docker compose stack.
 * On Windows, Playwright killing the webServer process tree does not stop
 * the containers themselves, so we do it explicitly here.
 */
const { spawnSync } = require('child_process');

module.exports = async () => {
  spawnSync(
    'docker',
    ['compose', '-f', 'docker-compose.test.yml', 'down', '--remove-orphans'],
    { cwd: __dirname, stdio: 'inherit' }
  );
};
