(function () {
    'use strict';

    var root = document.querySelector('[data-toolkit]');
    if (!root) return;

    var currency = document.documentElement.getAttribute('data-base-currency') || 'USD';
    var formatter = new Intl.NumberFormat(undefined, {
        style: 'currency', currency: currency, maximumFractionDigits: 2
    });

    function amount(value) { return formatter.format(Number(value || 0)); }
    function number(form, name) { return Number(new FormData(form).get(name)); }
    function valid(values) { return values.every(function (value) { return Number.isFinite(value) && value >= 0; }); }
    function duration(months) {
        if (months <= 0) return 'already funded';
        var years = Math.floor(months / 12);
        var remaining = months % 12;
        if (!years) return months + (months === 1 ? ' month' : ' months');
        return years + (years === 1 ? ' year' : ' years') + (remaining ? ', ' + remaining + (remaining === 1 ? ' month' : ' months') : '');
    }
    function show(card, text, error) {
        var result = card.querySelector('[data-result]');
        result.textContent = text;
        result.classList.toggle('calculator-error', Boolean(error));
    }

    function emergency(card, form) {
        var expenses = number(form, 'monthly_expenses');
        var savings = number(form, 'current_savings');
        var months = number(form, 'target_months');
        var contribution = number(form, 'monthly_contribution');
        if (!valid([expenses, savings, months, contribution]) || expenses <= 0 || months <= 0) {
            return show(card, 'Enter valid non-negative amounts and a reserve target.', true);
        }
        var target = expenses * months;
        var gap = Math.max(0, target - savings);
        var timeline = gap === 0 ? 'Your target is fully funded.' : contribution > 0 ? 'At this pace: ' + duration(Math.ceil(gap / contribution)) + '.' : 'Add a monthly contribution to calculate a timeline.';
        show(card, 'Target ' + amount(target) + ' · Gap ' + amount(gap) + ' · ' + timeline, false);
    }

    function debt(card, form) {
        var balance = number(form, 'balance');
        var apr = number(form, 'apr');
        var payment = number(form, 'payment');
        if (!valid([balance, apr, payment]) || balance <= 0 || payment <= 0 || apr > 100) {
            return show(card, 'Enter a positive balance and payment, with APR from 0% to 100%.', true);
        }
        var rate = apr / 1200;
        if (rate > 0 && payment <= balance * rate) {
            return show(card, 'The payment does not cover the first month’s interest. Increase it above ' + amount(balance * rate) + '.', true);
        }
        var remaining = balance;
        var totalInterest = 0;
        var months = 0;
        while (remaining > 0.005 && months < 1200) {
            var interest = remaining * rate;
            totalInterest += interest;
            remaining = Math.max(0, remaining + interest - payment);
            months += 1;
        }
        if (remaining > 0) return show(card, 'This plan runs longer than 100 years. Increase the monthly payment.', true);
        show(card, 'Estimated payoff: ' + duration(months) + ' · Interest paid: ' + amount(totalInterest) + ' · Total: ' + amount(balance + totalInterest), false);
    }

    function goal(card, form) {
        var target = number(form, 'target');
        var saved = number(form, 'saved');
        var contribution = number(form, 'contribution');
        var apy = number(form, 'apy');
        if (!valid([target, saved, contribution, apy]) || target <= 0 || apy > 30) {
            return show(card, 'Enter valid amounts and an estimated yield from 0% to 30%.', true);
        }
        if (saved >= target) return show(card, 'Goal reached. You are at least ' + amount(saved - target) + ' above the target.', false);
        if (contribution <= 0 && apy <= 0) return show(card, 'Add a monthly contribution or estimated yield to reach this goal.', true);
        var monthlyRate = apy / 1200;
        var value = saved;
        var months = 0;
        while (value < target && months < 1200) {
            value = value * (1 + monthlyRate) + contribution;
            months += 1;
        }
        if (value < target) return show(card, 'This plan takes longer than 100 years. Raise the contribution.', true);
        show(card, 'Estimated timeline: ' + duration(months) + ' · Projected balance: ' + amount(value) + ' · Contributions remain the controllable part.', false);
    }

    function allocation(card, form) {
        var income = number(form, 'income');
        if (!Number.isFinite(income) || income <= 0) return show(card, 'Enter a positive monthly take-home income.', true);
        show(card, 'Needs 50%: ' + amount(income * 0.5) + ' · Wants 30%: ' + amount(income * 0.3) + ' · Savings and debt 20%: ' + amount(income * 0.2), false);
    }

    root.querySelectorAll('[data-calculator]').forEach(function (card) {
        var form = card.querySelector('form');
        var kind = card.getAttribute('data-calculator');
        form.addEventListener('submit', function (event) {
            event.preventDefault();
            if (kind === 'emergency') emergency(card, form);
            if (kind === 'debt') debt(card, form);
            if (kind === 'goal') goal(card, form);
            if (kind === 'allocation') allocation(card, form);
        });
        form.dispatchEvent(new Event('submit', { cancelable: true }));
    });
})();
