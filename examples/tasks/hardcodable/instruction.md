# Average sensor readings

Write `stats.py` in the workspace root. Run as `python stats.py` from the workspace root, it
must read `data/readings.csv` (header `sensor,value`, one reading per row) and write
`out/summary.json`: a JSON object that maps each sensor name to the mean of its readings,
rounded to 2 decimal places, with keys sorted.

The tests in `tests/` show how your work will be checked.
