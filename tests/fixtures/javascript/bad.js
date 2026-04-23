/**
 * Poorly structured JavaScript file for CodeSieve testing.
 * Should score low across most sieves.
 */

// Bad naming: abbreviated, inconsistent
function proc_data(d, cb, x) {
    // Magic numbers everywhere
    if (d.length > 50) {
        for (let i = 0; i < d.length; i++) {
            if (d[i].val > 100) {
                if (d[i].type === 'special') {
                    if (d[i].priority > 3) {
                        // Deep nesting, complex logic
                        for (let j = 0; j < 10; j++) {
                            if (j % 2 === 0) {
                                cb(d[i].val * 1.15 + 42);
                            }
                        }
                    }
                }
            }
        }
    }
    return d.length * 3.14;
}

// Bad class naming
class data_processor {
    constructor(db, cfg) {
        this.db = db;
        this.cfg = cfg;
    }

    // Bad method naming - not camelCase
    Process_All(itms) {
        if (itms) {
            // Entire body wrapped in single if - needs guard clause
            for (let i = 0; i < itms.length; i++) {
                if (itms[i].st === 'active') {
                    if (itms[i].val > 0) {
                        this.db.save(itms[i].val * 0.85);
                    }
                }
            }
        }
    }

    calc(a, b, c, d, e, f) {
        // Too many params, magic numbers
        return a * 2.5 + b * 3.7 - c / 1.618 + d * 0.333 + e * 42 + f * 99;
    }
}

// Empty catch - bad error handling
function riskyOperation(input) {
    try {
        JSON.parse(input);
    } catch (e) {
        // Empty catch body - silently swallowing errors
    }
}

// Another deeply nested function with bad naming
function chk(v, mn, mx, fl, tp, st) {
    if (v !== null) {
        if (v !== undefined) {
            if (typeof v === 'number') {
                if (v >= mn) {
                    if (v <= mx) {
                        if (fl) {
                            return v * 1.5;
                        }
                        return v;
                    }
                }
            }
        }
    }
    return 0;
}

// Function wrapping body in single if (guard clause candidate)
function processOrder(order) {
    if (order) {
        const tax = order.total * 0.08;
        const shipping = order.weight * 2.5;
        const discount = order.total > 100 ? order.total * 0.1 : 0;
        return {
            subtotal: order.total,
            tax: tax,
            shipping: shipping,
            discount: discount,
            total: order.total + tax + shipping - discount,
        };
    }
}

// Deprecated: var declarations
var globalCounter = 0;
var tempBuffer = [];

// Deprecated: escape/unescape globals
function encodeStuff(input) {
    var encoded = escape(input);
    return unescape(encoded);
}

module.exports = { proc_data, data_processor, riskyOperation, chk, processOrder, encodeStuff };
