# Individual report analyses (Wiebke Walkden)

Scripts for the additional analyses in the individual report: Stage 6/7
pipeline, cost decomposition (locked vs. surprise), QUARTER_ONLY run,
event sensitivity and report Figures 1-6.

Run in this order, in one folder together with all CSV files of the
case-study data set:

metrics.py -> m2.py -> m3.py -> m4.py -> m5.py -> figs.py -> figs2.py

Each script saves an intermediate result (grid.pkl -> grid2.pkl ->
grid3.pkl) for the next one. stage67_figures.py is imported as a module
and must be in the same folder. figs.py and figs2.py write to the path
in the variable OUT; change it to a local folder before running.

The scripts were generated with Claude (Anthropic); see the AI directory
in the report appendix.
