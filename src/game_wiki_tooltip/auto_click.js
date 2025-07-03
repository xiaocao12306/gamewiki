(function () {
  const TARGET_HOST = "{{DOMAIN}}";     // 运行时用 Python 替换
  const CLICK_DELAY = 600;              // 页面初步渲染完成的等待时间(ms)
  const MAX_OBS_TIME = 7000;            // 7 秒后停掉 Observer，避免死循环

  let clicked = false, observer = null;

  // 日志函数，同时输出到控制台和Python
  function log(msg) {
    console.log('[Overlay]', msg);
    if (window.pywebview && window.pywebview.api) {
      try {
        window.pywebview.api.log(msg);
      } catch (e) {
        // 忽略js_api错误
      }
    }
  }

  log('脚本开始执行，目标域名: ' + TARGET_HOST);
  log('当前页面URL: ' + window.location.href);
  log('页面标题: ' + document.title);

  // 解析 Bing 跳转链接，提取真实 URL
  function realUrl(a) {
    // data-href 优先
    const dh = a.getAttribute('data-href');
    if (dh) return dh;

    try {
      const bing = new URL(a.href, location.origin);
      let u = bing.searchParams.get('u') || bing.searchParams.get('r');
      if (u) {
        u = decodeURIComponent(u);     // 先 URL-decode
        u = tryBase64Decode(u);        // 再检测并解 base64
        log('解码后的真实URL: ' + u);
        return u;
      }
    } catch (e) { 
      log('解析URL失败: ' + e);
    }

    // 最后兜底
    return a.href;
  }

  // 尝试base64解码
  function tryBase64Decode(str) {
    // a1 / a2 … → 去掉前缀再 atob
    if (/^a\d[A-Za-z0-9+/=_-]+$/.test(str)) {
      const raw = str.slice(2)                       // 去掉 a1
                     .replace(/-/g, '+')
                     .replace(/_/g, '/');
      try {
        const decoded = atob(raw);
        log('Base64解码成功: ' + decoded);
        return decoded;
      } catch (e) { 
        log('Base64解码失败: ' + e);
      }
    }
    return str;
  }

  // 判断是否符合"合法搜索结果"
  function isValid(link) {
    if (!link) {
      log('链接为空，无效');
      return false;
    }
    
    // 检查是否是广告
    if (link.closest('.b_ad, .b_ans, .b_algoSponsored')) {
      log('链接在广告区域，无效');
      return false;
    }

    try {
      // 使用realUrl获取真实URL，然后检查域名
      const realTarget = realUrl(link);
      log('检查真实URL: ' + realTarget);
      
      const host = new URL(realTarget).hostname;
      log('提取的域名: ' + host + ', 目标域名: ' + TARGET_HOST);
      
      const isValid = host.endsWith(TARGET_HOST);
      log('域名匹配结果: ' + isValid);
      return isValid;
    } catch (e) { 
      log('验证链接时出错: ' + e);
      return false; 
    }
  }

  // 找到有效链接后通过API返回给Python
  function findValidLink() {
    log('尝试查找搜索结果链接...');
    
    // 查找第一个搜索结果链接
    const link = document.querySelector('#b_results li.b_algo h2 a');
    if (link) {
      log('找到第一个搜索结果链接: ' + link.href);
      
      if (isValid(link)) {
        const real = realUrl(link);  // 直接使用解码后的真实URL，不进行二次编码
        log('找到有效链接: ' + real);
        return real;  // 直接给出目标站 URL
      } else {
        log('第一个链接无效，尝试查找其他链接...');
      }
    }
    
    // 如果第一个链接无效，查找所有链接
    const links = document.querySelectorAll(
      '#b_results li.b_algo h2 a, #b_results li.b_algo a'
    );
    log('找到 ' + links.length + ' 个搜索结果链接');
    
    // 检查每个链接
    for (let i = 0; i < links.length; i++) {
      const a = links[i];
      log('检查链接 ' + (i + 1) + ': ' + a.href);
      
      if (isValid(a)) {
        const real = realUrl(a);  // 直接使用解码后的真实URL，不进行二次编码
        log('找到有效链接: ' + real);
        return real;  // 直接给出目标站 URL
      }
    }
    
    log('没有找到有效的链接');
    return null;
  }

  // 点击时直接导航到链接URL
  function clickLink(a) {
    const target = a.href;
    log('准备在浮窗中打开: ' + target);

    // 优先走 pywebview（使用同一窗口，体验更好）
    if (window.pywebview && window.pywebview.api && window.pywebview.api.open_url) {
        log('使用 pywebview API 打开链接');
        window.pywebview.api.open_url(target)
          .then(res => log('API 调用结果: ' + res))
          .catch(err => {
            log('API 调用失败，fallback: ' + err);
            window.location.href = target;   // 兜底
          });
    } else {
        // 没有 js_api 时直接跳
        window.location.href = target;
    }
  }

  function tryClick() {
    if (clicked) {
      log('已经处理过，跳过');
      return true;
    }

    const validLink = findValidLink();
    if (validLink) {
      log('找到有效链接，通过API返回: ' + validLink);
      clicked = true;
      
      // 通过API返回有效链接给Python
      if (window.pywebview && window.pywebview.api && window.pywebview.api.found_valid_link) {
        log('调用found_valid_link API...');
        window.pywebview.api.found_valid_link(validLink)
          .then(res => {
            log('API返回结果: ' + res);
            if (res === 'ok' || res === 'ok-new') {
              log('链接加载成功');
            } else {
              log('链接加载失败: ' + res);
            }
          })
          .catch(err => {
            log('API调用失败: ' + err);
            log('尝试使用备用方法...');
            // 备用方法：直接在当前窗口打开
            window.location.href = validLink;
          });
      } else {
        log('API不可用，使用备用方法');
        window.location.href = validLink;
      }
      return true;
    }
    
    log('没有找到有效的链接');
    return false;
  }

  // MutationObserver：Bing 懒加载或排序变化时再试一次
  function attachObserver() {
    if (observer) return;
    log('添加DOM监听器');
    observer = new MutationObserver((mutations) => {
      log('DOM变化，变化数量: ' + mutations.length);
      for (let mutation of mutations) {
        log('变化类型: ' + mutation.type + ', 添加节点数: ' + mutation.addedNodes.length);
      }
      tryClick();
    });
    observer.observe(document.querySelector('#b_content') || document.body,
                     { childList: true, subtree: true });
    // 7 s 后停止监听
    setTimeout(() => {
      if (observer) {
        log('停止DOM监听器');
        observer.disconnect();
      }
    }, MAX_OBS_TIME);
  }

  // 检查搜索结果是否来自目标域名，如果不是则重新提交搜索
  function checkAndResubmitSearch() {
    log('检查搜索结果是否来自目标域名...');
    
    // 检查是否已经重新提交过，避免无限循环
    if (window._resubmitted) {
      log('已经重新提交过，跳过检查');
      return;
    }
    
    // 等待搜索结果加载
    setTimeout(() => {
      const firstResult = document.querySelector('#b_results > li.b_algo a');
      if (firstResult) {
        log('找到第一个搜索结果: ' + firstResult.href);
        
        try {
          const realTarget = realUrl(firstResult);
          const host = new URL(realTarget).hostname;
          log('第一个结果的域名: ' + host + ', 目标域名: ' + TARGET_HOST);
          
          // 检查是否来自目标域名
          if (!host.endsWith(TARGET_HOST)) {
            log('第一个结果不是来自目标域名，重新提交搜索表单');
            
            // 标记已重新提交，避免无限循环
            window._resubmitted = true;
            
            // 查找搜索表单并重新提交
            const form = document.querySelector('#sb_form');
            if (form) {
              log('找到搜索表单，重新提交');
              // 确保搜索框中有正确的查询内容
              const searchInput = document.querySelector('#sb_form_q, input[name="q"]');
              if (searchInput) {
                const currentQuery = searchInput.value;
                log('当前搜索查询: ' + currentQuery);
                // 如果查询中没有site:限制，添加它
                if (!currentQuery.includes('site:' + TARGET_HOST)) {
                  const newQuery = currentQuery + ' site:' + TARGET_HOST;
                  searchInput.value = newQuery;
                  log('更新搜索查询为: ' + newQuery);
                }
              }
              form.submit();
            } else {
              log('未找到搜索表单');
            }
          } else {
            log('第一个结果来自目标域名，无需重新提交');
          }
        } catch (e) {
          log('检查域名时出错: ' + e);
        }
      } else {
        log('未找到搜索结果，可能还在加载中');
      }
    }, 1500); // 等待1.5秒让搜索结果加载
  }

  // 主流程
  function run() {
    log('开始主流程');
    log('当前页面状态: readyState=' + document.readyState);
    log('页面内容长度: ' + document.body.innerHTML.length);
    log('当前页面URL: ' + window.location.href);
    
    // 检查是否在Bing搜索结果页面
    if (!window.location.href.includes('bing.com/search')) {
      log('不在Bing搜索结果页面，跳过自动点击');
      return;
    }
    
    if (tryClick()) {
      log('点击成功，流程结束');
      return;
    }
    
    log('点击失败，添加DOM监听器');
    attachObserver();
  }

  // 稍等渲染完成再开始
  window.addEventListener('load', () => {
    log('页面加载完成，等待 ' + CLICK_DELAY + ' ms后执行');
    setTimeout(run, CLICK_DELAY);
  });
  
  // 如果页面已经加载完成，立即执行
  if (document.readyState === 'complete') {
    log('页面已加载完成，立即执行');
    setTimeout(run, 100);
  }
  
  // 监听DOM变化，确保在搜索结果加载完成后再检查
  let domObserver = null;
  function setupDOMObserver() {
    if (domObserver) return;
    
    domObserver = new MutationObserver((mutations) => {
      // 检查是否有搜索结果出现
      const results = document.querySelectorAll('#b_results li.b_algo');
      if (results.length > 0) {
        log('检测到搜索结果出现，数量: ' + results.length);
        domObserver.disconnect();
        domObserver = null;
        
        // 延迟一点时间确保结果完全加载
        setTimeout(() => {
          if (!window._resubmitted) {
            checkAndResubmitSearch();
          }
        }, 500);
      }
    });
    
    domObserver.observe(document.body, { 
      childList: true, 
      subtree: true 
    });
    
    // 5秒后停止观察，避免无限等待
    setTimeout(() => {
      if (domObserver) {
        log('DOM观察器超时，停止观察');
        domObserver.disconnect();
        domObserver = null;
      }
    }, 5000);
  }
  
  // 在页面加载完成后设置DOM观察器
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', setupDOMObserver);
  } else {
    setupDOMObserver();
  }
})(); 