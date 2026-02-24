/**
 * Poorly structured TypeScript file for CodeSieve testing.
 * Should score low across most sieves.
 */

// Bad naming: abbreviated variables
function proc_data(d: any, cb: any, x: any): any {
    // Magic numbers everywhere
    if (d.length > 50) {
        for (let i = 0; i < d.length; i++) {
            if (d[i].val > 100) {
                if (d[i].type === 'special') {
                    if (d[i].priority > 3) {
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

// Bad class name - not PascalCase
class data_processor {
    private db: any;
    private cfg: any;

    constructor(db: any, cfg: any) {
        this.db = db;
        this.cfg = cfg;
    }

    // Bad method naming
    Process_All(itms: any[]): void {
        if (itms) {
            for (let i = 0; i < itms.length; i++) {
                if (itms[i].st === 'active') {
                    if (itms[i].val > 0) {
                        this.db.save(itms[i].val * 0.85);
                    }
                }
            }
        }
    }

    calc(a: number, b: number, c: number, d: number, e: number, f: number): number {
        return a * 2.5 + b * 3.7 - c / 1.618 + d * 0.333 + e * 42 + f * 99;
    }
}

// Missing type annotations on some params
function badTypes(name: string, value, count): number {
    return value * count;
}

// Missing return type
function noReturnType(input: string) {
    return input.toUpperCase();
}

// Empty catch - bad error handling
function riskyOperation(input: string): void {
    try {
        JSON.parse(input);
    } catch (e) {
        // Empty catch body
    }
}

// Deeply nested with bad naming
function chk(v: any, mn: number, mx: number, fl: boolean, tp: string, st: string): number {
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

// Guard clause candidate
function processOrder(order: any): any {
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

export { proc_data, data_processor, badTypes, noReturnType, riskyOperation, chk, processOrder };
