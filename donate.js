/* 打赏组件逻辑 —— 全站共享
 * 用法：在 <head> 引入 donate.css，在 </body> 前引入本文件，
 * 并通过 data-donate-img 属性指定二维码图片路径（默认 donate.png，相对当前页面）。
 */
(function () {
  var img = document.currentScript ? document.currentScript.getAttribute('data-donate-img') : null;
  if (!img) img = 'donate.png';

  var tipText = '☕ 这条情报，值碗汤钱';

  var pc = document.createElement('div');
  pc.id = 'donate-pc';
  pc.innerHTML =
    '<div class="d-title">为今天的判断买单</div>' +
    '<div class="d-sub">VALUE · 情报费</div>' +
    '<img src="' + img + '" alt="打赏码">' +
    '<div class="d-tip">这条情报帮你避的坑，够请十碗胡辣汤<br><strong>☕</strong></div>';

  var fab = document.createElement('button');
  fab.id = 'donate-fab';
  fab.type = 'button';
  fab.textContent = '☕ 这条情报，值碗汤钱';

  var modal = document.createElement('div');
  modal.id = 'donate-modal';
  modal.innerHTML =
    '<div class="dm-card">' +
    '<button class="dm-close" type="button" aria-label="关闭">✕</button>' +
    '<div class="dm-title">为今天的判断买单</div>' +
    '<div class="dm-sub">VALUE · 情报费</div>' +
    '<img src="' + img + '" alt="打赏码">' +
    '<div class="dm-tip">今天帮你避的坑，够请十碗胡辣汤<br><strong>☕</strong></div>' +
    '</div>';

  document.body.appendChild(pc);
  document.body.appendChild(fab);
  document.body.appendChild(modal);

  function openModal() { modal.classList.add('show'); }
  function closeModal() { modal.classList.remove('show'); }
  fab.addEventListener('click', openModal);
  modal.querySelector('.dm-close').addEventListener('click', closeModal);
  modal.addEventListener('click', function (e) { if (e.target === modal) closeModal(); });
})();
