(function () {
    'use strict';

    var samples = {
        '30d': { income: '$6,140', expenses: '$4,080', net: '+$2,060', score: '79' },
        '90d': { income: '$18,420', expenses: '$11,780', net: '+$6,640', score: '82' },
        ytd: { income: '$42,860', expenses: '$27,310', net: '+$15,550', score: '86' }
    };

    document.querySelectorAll('[data-period]').forEach(function (button) {
        button.addEventListener('click', function () {
            var sample = samples[button.getAttribute('data-period')];
            if (!sample) return;
            document.querySelectorAll('[data-period]').forEach(function (item) {
                item.classList.toggle('active', item === button);
            });
            Object.keys(sample).forEach(function (key) {
                var target = document.querySelector('[data-metric="' + key + '"]');
                if (!target) return;
                if (key === 'score') {
                    target.innerHTML = sample[key] + '<span>/100</span>';
                } else {
                    target.textContent = sample[key];
                }
            });
        });
    });

    var year = document.getElementById('year');
    if (year) year.textContent = String(new Date().getFullYear());
})();
