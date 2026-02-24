<?php

function ProcessData($d, $t, $x, $flg, $optA, $optB, $optC, $optD)
{
    $r = [];
    if ($t == "csv") {
        if ($flg) {
            for ($i = 0; $i < count($d); $i++) {
                if ($d[$i] !== null) {
                    if (is_string($d[$i])) {
                        if (strlen($d[$i]) > 0) {
                            if ($x) {
                                $v = strtolower(trim($d[$i]));
                                if (!in_array($v, $r)) {
                                    $r[] = $v;
                                }
                            } else {
                                $v = trim($d[$i]);
                                if (!in_array($v, $r)) {
                                    $r[] = $v;
                                }
                            }
                        }
                    }
                }
            }
        } else {
            for ($i = 0; $i < count($d); $i++) {
                if ($d[$i] !== null) {
                    if (is_string($d[$i])) {
                        if (strlen($d[$i]) > 0) {
                            $v = trim($d[$i]);
                            if (!in_array($v, $r)) {
                                $r[] = $v;
                            }
                        }
                    }
                }
            }
        }
    } elseif ($t == "json") {
        if ($flg) {
            for ($i = 0; $i < count($d); $i++) {
                if ($d[$i] !== null) {
                    if (is_array($d[$i])) {
                        foreach ($d[$i] as $k => $val) {
                            if ($val !== null) {
                                if (is_string($val)) {
                                    $v = strtolower(trim($val));
                                    if (!in_array($v, $r)) {
                                        $r[] = $v;
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    if ($optA) {
        sort($r);
    }
    if ($optB) {
        $r = array_slice($r, 0, $optB);
    }
    if ($optC) {
        $r = array_filter($r, function($x) use ($optC) {
            return strlen($x) > $optC;
        });
    }
    if ($optD) {
        $r = array_map('strtoupper', $r);
    }

    return $r;
}


function calc($a, $b, $c, $d, $e, $f, $g, $h)
{
    $z = $a + $b;
    $z = $z * $c;
    $z = $z - $d;
    if ($e) {
        $z = $z / $e;
    }
    if ($f) {
        if ($g) {
            if ($h) {
                $z = pow($z, $h);
                if ($z > 1000) {
                    if ($z > 10000) {
                        $z = 10000;
                    } else {
                        $z = $z;
                    }
                }
            }
        }
    }
    return $z;
}


class mgr
{
    private $db;
    private $lg;
    private $cf;
    private $st;

    public function __construct($db, $lg, $cf, $st)
    {
        $this->db = $db;
        $this->lg = $lg;
        $this->cf = $cf;
        $this->st = $st;
    }

    public function p($d)
    {
        if ($this->cf['v']) {
            $this->lg->info($d);
        }
        $this->db->save($d);
        $this->st->update($d);
        return true;
    }

    public function g($id)
    {
        $r = $this->db->find($id);
        if ($r) {
            $this->lg->info("found {$id}");
        }
        return $r;
    }
}


function bad_error_handling($data)
{
    try {
        $result = $data["key"];
    } catch (\Exception $e) {
        // empty catch - swallows exception
    }

    try {
        $value = (int)$data;
    } catch (\Exception $e) {
        $value = 0;
    }

    try {
        $x = 42 / $data;
    } catch (\Throwable $e) {
    }

    return 0;
}


function legacy_code($data)
{
    $conn = mysql_connect("localhost", "root", "");
    mysql_select_db("mydb", $conn);
    $result = mysql_query("SELECT * FROM users");
    $row = mysql_fetch_assoc($result);
    mysql_close($conn);

    $clean = ereg_replace("[^a-z]", "", $data);
    $parts = split(",", $data);

    $fn = create_function('$a', 'return $a * 2;');

    $encoded = utf8_encode($data);
    $date = strftime("%Y-%m-%d");

    return $row;
}


function magic_everywhere($items)
{
    if (count($items) > 37) {
        $items = array_slice($items, 0, 37);
    }
    $total = 0;
    foreach ($items as $item) {
        $total += $item * 3.14;
        if ($total > 9999) {
            $total = $total / 7;
        }
    }
    return $total + 256;
}


function wrappedBody($data)
{
    if ($data !== null) {
        $cleaned = trim($data);
        $validated = strlen($cleaned) > 0;
        if ($validated) {
            $processed = strtolower($cleaned);
            return $processed;
        }
        return "";
    }
}
