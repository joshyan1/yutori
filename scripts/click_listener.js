(function() {
    document.addEventListener('click', async function(event) {
        // Get the clicked element
        const element = event.target;
        
        // Build DOM path
        function getDomPath(el) {
            const stack = [];
            while (el.parentNode != null) {
                let sibCount = 0;
                let sibIndex = 0;
                for (let i = 0; i < el.parentNode.childNodes.length; i++) {
                    const sib = el.parentNode.childNodes[i];
                    if (sib.nodeName === el.nodeName) {
                        if (sib === el) {
                            sibIndex = sibCount;
                        }
                        sibCount++;
                    }
                }
                
                const tagName = el.nodeName.toLowerCase();
                const id = el.id ? `#${el.id}` : '';
                const classes = el.className ? `.${el.className.split(' ').join('.')}` : '';
                
                if (id) {
                    stack.unshift(tagName + id);
                } else if (sibCount > 1) {
                    stack.unshift(`${tagName}${classes}:nth-of-type(${sibIndex + 1})`);
                } else {
                    stack.unshift(tagName + classes);
                }
                
                el = el.parentNode;
            }
            
            return stack.join(' > ');
        }
        
        // Try to get a CSS selector for the element
        function getSelector(el) {
            if (el.id) return `#${el.id}`;
            if (el.className) {
                const classes = el.className.split(' ').filter(c => c).join('.');
                if (classes) return `.${classes}`;
            }
            return el.tagName.toLowerCase();
        }
        
        try {
            // Immediately notify Python about the click
            await window.notify_click({
                x: event.clientX,
                y: event.clientY,
                selector: getSelector(element),
                domPath: getDomPath(element),
                timestamp: Date.now()
            });
            console.log('Click notification sent successfully');
        } catch (err) {
            console.error('Error notifying click:', err);
        }
    }, true);
    
    console.log('Async click listener initialized');
})();
  