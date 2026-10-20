/* Dynamic import also works with an already-cached, classic-script template. */
import('./hall-app.js').catch(() => {
  const main = document.getElementById('main');
  const message = document.createElement('div');
  message.className = 'state-box';
  message.setAttribute('role', 'alert');
  const heading = document.createElement('h2');
  heading.textContent = '页面组件未能加载';
  const detail = document.createElement('p');
  detail.textContent = '请刷新页面重试，并确认本地静态文件完整。';
  const reload = document.createElement('button');
  reload.className = 'button';
  reload.type = 'button';
  reload.textContent = '刷新页面';
  reload.addEventListener('click', () => location.reload());
  message.append(heading, detail, reload);
  main.replaceChildren(message);
});
