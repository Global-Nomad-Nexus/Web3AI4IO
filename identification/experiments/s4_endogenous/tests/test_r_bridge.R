# S4 R-bridge tests: deterministic fixture through the production estimation path.
# Usage: Rscript test_r_bridge.R <experiment_root>
# Covers: deterministic ATT recovery (TWFE + CS e=0), universal base period,
# continuous event times, sensitivity nesting (Mbar=0.5 subset of Mbar=2),
# unestimable flagging on broken event-time support.

args <- commandArgs(trailingOnly = TRUE)
root <- args[1]
.libPaths(c(file.path(root, "R", "library"), .libPaths()))
suppressMessages({library(did); library(HonestDiD)})

n_ids <- 400; n_t <- 60; effect <- 0.20
set.seed(99)
g <- sample(c(0L, 25:32), n_ids, replace = TRUE,
            prob = c(0.6, rep(0.4 / 8, 8)))
alpha <- rnorm(n_ids)
lambda <- sin(1:n_t / 5) * 0.1
y <- sapply(seq_len(n_ids), function(i)
  alpha[i] + lambda + effect * as.integer(g[i] > 0 & 1:n_t >= g[i]) +
  rnorm(n_t, sd = 0.3))

batch <- file.path(root, "artifacts", "_rbridge_test")
dir.create(batch, showWarnings = FALSE, recursive = TRUE)
con <- file(file.path(batch, "y.bin"), "wb")
writeBin(as.double(y), con, size = 8, endian = "little"); close(con)
con <- file(file.path(batch, "g.bin"), "wb")
writeBin(as.integer(g), con, size = 4, endian = "little"); close(con)
write.csv(data.frame(n_reps = 1, n_ids = n_ids, n_t = n_t),
          file.path(batch, "shape.csv"), row.names = FALSE)
write.csv(data.frame(rep_id = 0L), file.path(batch, "rep_ids.csv"), row.names = FALSE)

out_csv <- file.path(batch, "out.csv")
env <- paste0("R_LIBS=", file.path(root, "R", "library"))
status <- system2("Rscript", c(file.path(root, "R", "estimate_batch.R"),
                               batch, out_csv, "2"), env = env)
stopifnot(status == 0)
r <- read.csv(out_csv, check.names = FALSE)

ok <- function(name, cond, detail = "") {
  stopifnot(isTRUE(cond))
  cat("pass:", name, detail, "\n")
}

ok("estimable", r$unestimable == 0, r$fail_reason)
ok("twfe_recovers_effect", abs(r$twfe_est - effect) < 0.05, sprintf("%.6f", r$twfe_est))
ok("cs_recovers_effect", abs(r$cs_att_e0 - effect) < 0.05, sprintf("%.6f", r$cs_att_e0))
ok("original_ci_covers_truth", r$orig_lb <= effect & r$orig_ub >= effect)
ok("sensitivity_nesting",
   r$rm_lb_2 <= r$rm_lb_1.5 + 1e-12 && r$rm_lb_1.5 <= r$rm_lb_1 + 1e-12 &&
   r$rm_lb_1 <= r$rm_lb_0.5 + 1e-12 && r$rm_ub_0.5 <= r$rm_ub_1 + 1e-12 &&
   r$rm_ub_1 <= r$rm_ub_1.5 + 1e-12 && r$rm_ub_1.5 <= r$rm_ub_2 + 1e-12)
ok("robust_intervals_finite_and_nonempty",
   all(is.finite(c(r$rm_lb_0.5, r$rm_ub_0.5, r$rm_lb_1, r$rm_ub_1,
                   r$rm_lb_1.5, r$rm_ub_1.5, r$rm_lb_2, r$rm_ub_2))) &&
   r$rm_ub_1 > r$rm_lb_1)
ok("pretrend_test_not_significant_on_flat_fixture", r$pretrend_wald_p > 0.05,
   sprintf("p=%.3f", r$pretrend_wald_p))
ok("robust_value_finite_or_inf", !is.na(r$robust_value))

# broken support must be flagged unestimable, not silently re-estimated
g2 <- g; g2[g2 == 25] <- 3L   # cohort at t=3 -> no e=-7 support
con <- file(file.path(batch, "g.bin"), "wb")
writeBin(as.integer(g2), con, size = 4, endian = "little"); close(con)
status <- system2("Rscript", c(file.path(root, "R", "estimate_batch.R"),
                               batch, out_csv, "2"), env = env)
stopifnot(status == 0)
r2 <- read.csv(out_csv, check.names = FALSE)
ok("broken_support_marked_unestimable",
   r2$unestimable == 1 || all(-7:7 %in% NA),
   ifelse(r2$unestimable == 1, r2$fail_reason, "NOT FLAGGED"))

unlink(batch, recursive = TRUE)
cat("All R-bridge tests passed.\n")
