#!/usr/bin/env Rscript

args <- commandArgs(trailingOnly = FALSE)
file_arg <- "--file="
script_path <- normalizePath(sub(file_arg, "", args[grep(file_arg, args)]), mustWork = FALSE)
script_dir <- dirname(script_path)
repo_root <- normalizePath(file.path(script_dir, "..", ".."), mustWork = TRUE)
stress_root <- file.path(repo_root, "phase_2", "reference", "Stress")
output_dir <- file.path(repo_root, "phase_2", "analysis", "outputs")
dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)

features <- c(
  "hrrange", "hrvar", "hrstd", "hrmin", "edarange",
  "edastd", "edavar", "hrkurt", "edamin", "hrmax"
)

read_zip_csv <- function(zip_path, csv_name) {
  con <- unz(zip_path, csv_name)
  on.exit(try(close(con), silent = TRUE))
  data <- read.csv(con, stringsAsFactors = FALSE)
  names(data) <- tolower(names(data))
  data
}

source_from_subject <- function(subject) {
  prefix <- substr(subject, 1, 1)
  source <- ifelse(prefix == "N", "NEURO",
    ifelse(prefix == "S", "SWELL",
      ifelse(prefix == "U", "UBFC",
        ifelse(prefix == "W", "WESAD",
          ifelse(prefix == "X", "SYNTHETIC", "UNKNOWN")
        )
      )
    )
  )
  source
}

auc_score <- function(y, score) {
  y <- as.integer(y)
  ok <- is.finite(score) & !is.na(y)
  y <- y[ok]
  score <- score[ok]
  pos <- y == 1
  neg <- y == 0
  n_pos <- as.numeric(sum(pos))
  n_neg <- as.numeric(sum(neg))
  if (n_pos == 0 || n_neg == 0) return(NA_real_)
  ranks <- rank(score, ties.method = "average")
  (sum(ranks[pos]) - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg)
}

accuracy_score <- function(y, score, threshold = 0.5) {
  pred <- ifelse(score >= threshold, 1L, 0L)
  mean(pred == as.integer(y), na.rm = TRUE)
}

brier_score <- function(y, score) {
  mean((as.numeric(y) - score)^2, na.rm = TRUE)
}

class_weights <- function(y) {
  y <- as.integer(y)
  n <- length(y)
  n0 <- sum(y == 0)
  n1 <- sum(y == 1)
  weights <- rep(1, n)
  if (n0 > 0) weights[y == 0] <- n / (2 * n0)
  if (n1 > 0) weights[y == 1] <- n / (2 * n1)
  weights
}

scale_train_test <- function(train, test) {
  for (feature in features) {
    center <- mean(train[[feature]], na.rm = TRUE)
    spread <- sd(train[[feature]], na.rm = TRUE)
    if (!is.finite(spread) || spread == 0) spread <- 1
    train[[feature]] <- (train[[feature]] - center) / spread
    test[[feature]] <- (test[[feature]] - center) / spread
  }
  list(train = train, test = test)
}

fit_glm_scores <- function(train, test, balanced = FALSE) {
  scaled <- scale_train_test(train, test)
  train <- scaled$train
  test <- scaled$test
  formula <- as.formula(paste("metric ~", paste(features, collapse = " + ")))
  weights <- if (balanced) class_weights(train$metric) else rep(1, nrow(train))
  model <- suppressWarnings(glm(formula, data = train, family = binomial(), weights = weights))
  scores <- suppressWarnings(predict(model, newdata = test, type = "response"))
  pmin(pmax(scores, 0), 1)
}

fit_rpart_scores <- function(train, test, balanced = FALSE) {
  if (!requireNamespace("rpart", quietly = TRUE)) return(NULL)
  scaled <- scale_train_test(train, test)
  train <- scaled$train
  test <- scaled$test
  train$metric_factor <- factor(train$metric, levels = c(0, 1))
  formula <- as.formula(paste("metric_factor ~", paste(features, collapse = " + ")))
  weights <- if (balanced) class_weights(train$metric) else rep(1, nrow(train))
  model <- rpart::rpart(
    formula,
    data = train,
    method = "class",
    weights = weights,
    control = rpart::rpart.control(cp = 0.002, minbucket = 50)
  )
  scores <- predict(model, newdata = test, type = "prob")[, "1"]
  pmin(pmax(scores, 0), 1)
}

evaluate <- function(train, test, experiment, train_condition, test_condition) {
  models <- list(
    glm_unweighted = fit_glm_scores(train, test, balanced = FALSE),
    glm_balanced = fit_glm_scores(train, test, balanced = TRUE)
  )
  rows <- list()
  for (model_name in names(models)) {
    scores <- models[[model_name]]
    if (is.null(scores)) next
    rows[[length(rows) + 1]] <- data.frame(
      experiment = experiment,
      train_condition = train_condition,
      test_condition = test_condition,
      model = model_name,
      train_rows = nrow(train),
      test_rows = nrow(test),
      train_subjects = length(unique(train$subject)),
      test_subjects = length(unique(test$subject)),
      test_positive_rate = mean(test$metric == 1),
      auc = auc_score(test$metric, scores),
      accuracy = accuracy_score(test$metric, scores),
      brier = brier_score(test$metric, scores),
      stringsAsFactors = FALSE
    )
  }
  do.call(rbind, rows)
}

real <- read_zip_csv(file.path(stress_root, "StressData.zip"), "StressData.csv")
synthetic <- read_zip_csv(file.path(stress_root, "SynthesizedStressData.zip"), "SynthesizedStressData.csv")
real$dataset_id <- "stress_reference_real"
synthetic$dataset_id <- "stress_reference_synthetic"
real$source <- source_from_subject(real$subject)
synthetic$source <- source_from_subject(synthetic$subject)
real <- real[complete.cases(real[, c(features, "metric", "subject", "source")]), ]
synthetic <- synthetic[complete.cases(synthetic[, c(features, "metric", "subject", "source")]), ]

set.seed(20260429)
metrics <- list()

subject_holdout <- function(data, dataset_name) {
  subjects <- unique(data$subject)
  train_subjects <- sample(subjects, size = floor(length(subjects) * 0.7))
  train <- data[data$subject %in% train_subjects, ]
  test <- data[!(data$subject %in% train_subjects), ]
  evaluate(train, test, "subject_holdout", dataset_name, dataset_name)
}

metrics[[length(metrics) + 1]] <- subject_holdout(real, "real")
metrics[[length(metrics) + 1]] <- subject_holdout(synthetic, "synthetic")

for (held_out in sort(unique(real$source))) {
  test <- real[real$source == held_out, ]
  real_other <- real[real$source != held_out, ]
  combo <- rbind(real_other[, names(synthetic)], synthetic)
  metrics[[length(metrics) + 1]] <- evaluate(
    real_other, test, "source_transfer", "real_other", held_out
  )
  metrics[[length(metrics) + 1]] <- evaluate(
    synthetic, test, "source_transfer", "synthetic_only", held_out
  )
  metrics[[length(metrics) + 1]] <- evaluate(
    combo, test, "source_transfer", "real_other_plus_synthetic", held_out
  )
}

metrics <- do.call(rbind, metrics)
metrics_path <- file.path(output_dir, "stress_reference_r_metrics.csv")
write.csv(metrics, metrics_path, row.names = FALSE)

source_metrics <- metrics[metrics$experiment == "source_transfer", ]
lifts <- list()
for (model_name in unique(source_metrics$model)) {
  for (held_out in sort(unique(source_metrics$test_condition))) {
    base <- source_metrics[
      source_metrics$model == model_name &
        source_metrics$test_condition == held_out &
        source_metrics$train_condition == "real_other",
    ]
    synth <- source_metrics[
      source_metrics$model == model_name &
        source_metrics$test_condition == held_out &
        source_metrics$train_condition == "synthetic_only",
    ]
    combo <- source_metrics[
      source_metrics$model == model_name &
        source_metrics$test_condition == held_out &
        source_metrics$train_condition == "real_other_plus_synthetic",
    ]
    if (nrow(base) == 1 && nrow(synth) == 1 && nrow(combo) == 1) {
      lifts[[length(lifts) + 1]] <- data.frame(
        model = model_name,
        held_out_source = held_out,
        real_other_auc = base$auc,
        synthetic_auc = synth$auc,
        combo_auc = combo$auc,
        synthetic_auc_lift = synth$auc - base$auc,
        combo_auc_lift = combo$auc - base$auc,
        stringsAsFactors = FALSE
      )
    }
  }
}
lifts <- do.call(rbind, lifts)
lifts_path <- file.path(output_dir, "stress_reference_r_lifts.csv")
write.csv(lifts, lifts_path, row.names = FALSE)

audit <- data.frame(
  table = c("real", "synthetic"),
  rows = c(nrow(real), nrow(synthetic)),
  subjects = c(length(unique(real$subject)), length(unique(synthetic$subject))),
  positive_rate = c(mean(real$metric == 1), mean(synthetic$metric == 1)),
  stringsAsFactors = FALSE
)
audit_path <- file.path(output_dir, "stress_reference_r_audit.csv")
write.csv(audit, audit_path, row.names = FALSE)

cat("Wrote", metrics_path, "\n")
cat("Wrote", lifts_path, "\n")
cat("Wrote", audit_path, "\n")
cat("Rows:", nrow(real), "real and", nrow(synthetic), "synthetic\n")
