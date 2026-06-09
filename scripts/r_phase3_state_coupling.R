#!/usr/bin/env Rscript

# Phase 3 R exploration: state coupling, dropout-safe normalization, calibration risk.

options(warn = 1)

script_arg <- grep("^--file=", commandArgs(FALSE), value = TRUE)
script_path <- if (length(script_arg)) sub("^--file=", "", script_arg[[1]]) else "scripts/r_phase3_state_coupling.R"
root <- normalizePath(file.path(dirname(script_path), ".."), mustWork = FALSE)
repo_parent <- normalizePath(file.path(root, ".."), mustWork = FALSE)
parquet_path <- file.path(repo_parent, "_normalized/phase3/target_hz=1/window_features.parquet")
csv_path <- file.path(root, "outputs/phase3_r_compact.csv")
out_dir <- file.path(root, "outputs/r_phase3_state_coupling")
dir.create(out_dir, recursive = TRUE, showWarnings = FALSE)

log_line <- function(...) cat(paste0(..., "\n"))

read_phase3 <- function() {
  cols <- c(
    "dataset_id", "subject_id", "session_id", "label_family", "source_dataset",
    "condition", "baseline_state_bin", "target_pain_nrs_0_10", "target_stress_binary",
    "target_activity_binary", "target_baseline_binary", "target_confidence",
    "baseline_abs_delta_mean", "baseline_l2_delta",
    "bvp__mean", "hr__mean", "eda__mean", "temperature__mean", "acc__mag__mean",
    "respiration__mean", "emg__mean", "grip__mean",
    "bvp__present", "hr__present", "eda__present", "temperature__present", "acc__present",
    "respiration__present", "emg__present", "grip__present"
  )
  if (requireNamespace("duckdb", quietly = TRUE) && file.exists(parquet_path)) {
    con <- DBI::dbConnect(duckdb::duckdb(), dbdir = ":memory:")
    on.exit(DBI::dbDisconnect(con, shutdown = TRUE), add = TRUE)
    query <- paste0("select ", paste(cols, collapse = ","), " from read_parquet('", parquet_path, "')")
    result <- try(DBI::dbGetQuery(con, query), silent = TRUE)
    if (!inherits(result, "try-error")) return(result)
  }
  if (!file.exists(csv_path)) stop("No parquet read and no fallback CSV. Run scripts/export_phase3_for_r.py")
  read.csv(csv_path, stringsAsFactors = FALSE)
}

safe_num <- function(x) suppressWarnings(as.numeric(x))

robust_by_dataset <- function(df, feature_cols) {
  out <- df
  for (col in feature_cols) {
    zcol <- paste0(col, "__dataset_robust_z")
    out[[zcol]] <- NA_real_
    for (ds in unique(out$dataset_id)) {
      idx <- which(out$dataset_id == ds)
      x <- safe_num(out[[col]][idx])
      med <- median(x, na.rm = TRUE)
      madv <- median(abs(x - med), na.rm = TRUE) * 1.4826
      if (!is.finite(madv) || madv <= 1e-9) madv <- stats::sd(x, na.rm = TRUE)
      if (!is.finite(madv) || madv <= 1e-9) next
      out[[zcol]][idx] <- pmax(pmin((x - med) / madv, 8), -8)
    }
  }
  out
}

auc_rank <- function(y, score) {
  ok <- is.finite(y) & is.finite(score)
  y <- y[ok]; score <- score[ok]
  if (length(unique(y)) < 2) return(NA_real_)
  r <- rank(score, ties.method = "average")
  n1 <- as.numeric(sum(y == 1)); n0 <- as.numeric(sum(y == 0))
  (sum(r[y == 1]) - n1 * (n1 + 1) / 2) / (n1 * n0)
}

brier <- function(y, p) {
  ok <- is.finite(y) & is.finite(p)
  mean((p[ok] - y[ok])^2)
}

fit_glm_bin <- function(train, target, features) {
  keep <- complete.cases(train[, c(target, features), drop = FALSE])
  train <- train[keep, , drop = FALSE]
  if (nrow(train) < 200 || length(unique(train[[target]])) < 2) return(NULL)
  form <- stats::as.formula(paste(target, "~", paste(features, collapse = "+")))
  stats::glm(form, data = train, family = stats::binomial())
}

predict_bin <- function(model, test) {
  if (is.null(model)) return(rep(NA_real_, nrow(test)))
  as.numeric(stats::predict(model, newdata = test, type = "response"))
}

eval_group_holdout <- function(df, target, features, group_col = "dataset_id") {
  rows <- list()
  for (heldout in unique(df[[group_col]])) {
    train <- df[df[[group_col]] != heldout & is.finite(df[[target]]), , drop = FALSE]
    test <- df[df[[group_col]] == heldout & is.finite(df[[target]]), , drop = FALSE]
    model <- fit_glm_bin(train, target, features)
    pred <- predict_bin(model, test)
    rows[[length(rows) + 1]] <- data.frame(
      target = target,
      heldout = heldout,
      train_rows = nrow(train),
      test_rows = nrow(test),
      prevalence = mean(test[[target]], na.rm = TRUE),
      auc = auc_rank(test[[target]], pred),
      brier = brier(test[[target]], pred)
    )
  }
  do.call(rbind, rows)
}

softmax_states <- function(mat, temperature = 1.8) {
  z <- as.matrix(mat) / temperature
  z <- z - apply(z, 1, max, na.rm = TRUE)
  ez <- exp(z)
  ez / rowSums(ez)
}

df <- read_phase3()
log_line("rows=", nrow(df), " cols=", ncol(df))

for (col in names(df)) {
  if (grepl("__(mean|present)$|^target_|^baseline_", col)) df[[col]] <- safe_num(df[[col]])
}

feature_raw <- c(
  "bvp__mean", "hr__mean", "eda__mean", "temperature__mean", "acc__mag__mean",
  "respiration__mean", "emg__mean", "grip__mean", "baseline_abs_delta_mean", "baseline_l2_delta"
)
feature_raw <- intersect(feature_raw, names(df))
df <- robust_by_dataset(df, feature_raw)
feature_z <- paste0(feature_raw, "__dataset_robust_z")
feature_z <- feature_z[feature_z %in% names(df)]
present_cols <- intersect(c("bvp__present", "hr__present", "eda__present", "temperature__present", "acc__present", "respiration__present", "emg__present", "grip__present"), names(df))

model_features <- c(feature_z, present_cols)
for (col in model_features) df[[col]][!is.finite(df[[col]])] <- 0

df$pain_high_4_plus <- ifelse(is.finite(df$target_pain_nrs_0_10), as.integer(df$target_pain_nrs_0_10 >= 4), NA_integer_)
df$stress_bin <- ifelse(is.finite(df$target_stress_binary), as.integer(df$target_stress_binary > 0), NA_integer_)
df$activity_bin <- ifelse(is.finite(df$target_activity_binary), as.integer(df$target_activity_binary > 0), NA_integer_)
df$baseline_bin <- ifelse(is.finite(df$target_baseline_binary), as.integer(df$target_baseline_binary > 0), NA_integer_)
df$direct_pain <- df$label_family == "direct_pain" & is.finite(df$target_pain_nrs_0_10)

coverage <- aggregate(df[present_cols], list(dataset_id = df$dataset_id), mean, na.rm = TRUE)
write.csv(coverage, file.path(out_dir, "sensor_coverage_by_dataset.csv"), row.names = FALSE)

evals <- list()
evals[["pain"]] <- eval_group_holdout(df[df$direct_pain, , drop = FALSE], "pain_high_4_plus", model_features)
evals[["stress"]] <- eval_group_holdout(df[is.finite(df$stress_bin), , drop = FALSE], "stress_bin", model_features)
evals[["activity"]] <- eval_group_holdout(df[is.finite(df$activity_bin), , drop = FALSE], "activity_bin", model_features)
evals[["baseline"]] <- eval_group_holdout(df[is.finite(df$baseline_bin), , drop = FALSE], "baseline_bin", model_features)
eval_table <- do.call(rbind, evals)
write.csv(eval_table, file.path(out_dir, "leave_dataset_transfer_glm.csv"), row.names = FALSE)

stress_model <- fit_glm_bin(df[is.finite(df$stress_bin), , drop = FALSE], "stress_bin", model_features)
activity_model <- fit_glm_bin(df[is.finite(df$activity_bin), , drop = FALSE], "activity_bin", model_features)
baseline_model <- fit_glm_bin(df[is.finite(df$baseline_bin), , drop = FALSE], "baseline_bin", model_features)
pain_model <- fit_glm_bin(df[df$direct_pain, , drop = FALSE], "pain_high_4_plus", model_features)

df$stress_transfer <- predict_bin(stress_model, df)
df$activity_transfer <- predict_bin(activity_model, df)
df$baseline_transfer <- predict_bin(baseline_model, df)
df$pain_transfer <- predict_bin(pain_model, df)
df$baseline_departure_transfer <- 1 - df$baseline_transfer

state_mat <- cbind(
  pain = df$pain_transfer,
  stress = df$stress_transfer,
  activity = df$activity_transfer,
  baseline_departure = df$baseline_departure_transfer
)
state_mat[!is.finite(state_mat)] <- 0
state_probs <- softmax_states(state_mat, temperature = 1.6)
df$pain_pref_norm <- state_probs[, "pain"]
df$stress_pref_norm <- state_probs[, "stress"]
df$activity_pref_norm <- state_probs[, "activity"]
df$baseline_departure_pref_norm <- state_probs[, "baseline_departure"]
df$max_state_pref <- apply(state_probs, 1, max)

direct_summary <- aggregate(
  cbind(stress_transfer, activity_transfer, baseline_departure_transfer, pain_pref_norm, max_state_pref) ~ dataset_id + label_family,
  data = df[df$direct_pain, ],
  FUN = function(x) round(mean(x, na.rm = TRUE), 4)
)
write.csv(direct_summary, file.path(out_dir, "direct_pain_transfer_state_summary.csv"), row.names = FALSE)

cross_summary <- aggregate(
  cbind(pain_transfer, pain_pref_norm, stress_transfer, activity_transfer, baseline_departure_transfer, max_state_pref) ~ dataset_id + label_family,
  data = df,
  FUN = function(x) round(mean(x, na.rm = TRUE), 4)
)
write.csv(cross_summary, file.path(out_dir, "all_dataset_transfer_state_summary.csv"), row.names = FALSE)

df$pain_bins <- cut(df$target_pain_nrs_0_10, breaks = c(-Inf, 0, 4, 7, Inf), labels = c("zero", "mild", "moderate", "severe"))
bin_summary <- aggregate(
  cbind(stress_transfer, activity_transfer, baseline_departure_transfer, pain_pref_norm) ~ pain_bins,
  data = df[df$direct_pain & !is.na(df$pain_bins), ],
  FUN = function(x) round(mean(x, na.rm = TRUE), 4)
)
write.csv(bin_summary, file.path(out_dir, "pain_bins_vs_transfer_states.csv"), row.names = FALSE)

confidence_grid <- data.frame(raw_probability = seq(0, 1, by = 0.01))
confidence_grid$old_confidence_formula <- pmax(0.05, pmin(0.95, 0.5 * 1.0 + 0.5 * abs(confidence_grid$raw_probability - 0.5) * 2))
confidence_grid$conservative_confidence_formula <- pmax(0.05, pmin(0.9, (abs(confidence_grid$raw_probability - 0.5) * 2)^1.6))
write.csv(confidence_grid, file.path(out_dir, "confidence_formula_comparison.csv"), row.names = FALSE)

report <- file.path(out_dir, "R_PHASE3_STATE_COUPLING_REPORT.md")
sink(report)
cat("# R Phase 3 State Coupling Report\n\n")
cat("Rows:", nrow(df), "\n\n")
cat("## Sensor Coverage By Dataset\n\n")
print(coverage)
cat("\n## Leave-Dataset Transfer GLM\n\n")
print(eval_table)
cat("\n## Direct Pain Rows: Transferred State Means\n\n")
print(direct_summary)
cat("\n## Pain Bins vs Transferred States\n\n")
print(bin_summary)
cat("\n## Notes\n\n")
cat("- Robust dataset-normalized features used: median/MAD within dataset, clipped to +/-8.\n")
cat("- Present flags included, so dropout/missing sensor categories become learnable evidence, not fake zeros alone.\n")
cat("- State preference normalization = softmax over pain/stress/activity/baseline-departure logits; this forces competition between states.\n")
cat("- This is exploratory GLM, not final model. Use to choose next validation gates.\n")
sink()

log_line("wrote ", out_dir)
