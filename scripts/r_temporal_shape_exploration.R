#!/usr/bin/env Rscript

suppressPackageStartupMessages({
  library(DBI)
  library(duckdb)
})

args <- commandArgs(trailingOnly = TRUE)
output_dir <- if (length(args) >= 1) args[[1]] else "outputs/temporal_shape_r"
dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)

inputs <- data.frame(
  window_s = c(5, 10, 30),
  path = c(
    "outputs/temporal_shape_exploration_5s/temporal_shape_features.parquet",
    "outputs/temporal_shape_exploration_10s/temporal_shape_features.parquet",
    "outputs/temporal_shape_exploration/temporal_shape_features.parquet"
  ),
  stringsAsFactors = FALSE
)

auc_rank <- function(y, score) {
  keep <- is.finite(score) & !is.na(y)
  y <- y[keep]
  score <- score[keep]
  if (length(unique(y)) < 2) return(NA_real_)
  n1 <- sum(y == 1)
  n0 <- sum(y == 0)
  ranks <- rank(score, ties.method = "average")
  (sum(ranks[y == 1]) - n1 * (n1 + 1) / 2) / (n1 * n0)
}

feature_group <- function(name) {
  if (grepl("__base__", name, fixed = TRUE)) return("base")
  if (grepl("__shape__", name, fixed = TRUE)) return("shape")
  if (grepl("__shuffle__", name, fixed = TRUE)) return("shuffle")
  if (grepl("__reverse__", name, fixed = TRUE)) return("reverse")
  if (grepl("__coupling__", name, fixed = TRUE)) return("coupling")
  if (grepl("__quality__", name, fixed = TRUE)) return("quality")
  "other"
}

both_class_subjects <- function(y, subject_id) {
  split_y <- split(y, subject_id)
  sum(vapply(split_y, function(v) length(unique(v[!is.na(v)])) == 2, logical(1)))
}

safe_glm <- function(y, x, subject_id) {
  keep <- is.finite(x) & !is.na(y) & !is.na(subject_id)
  y <- y[keep]
  x <- x[keep]
  subject_id <- factor(subject_id[keep])
  if (length(y) < 40 || length(unique(y)) < 2 || sd(x) < 1e-12) {
    return(c(beta = NA_real_, p = NA_real_))
  }
  x <- as.numeric(scale(x))
  fit <- try(
    suppressWarnings(glm(y ~ x + subject_id, family = binomial())),
    silent = TRUE
  )
  if (inherits(fit, "try-error")) return(c(beta = NA_real_, p = NA_real_))
  coefficients <- summary(fit)$coefficients
  if (!("x" %in% rownames(coefficients))) return(c(beta = NA_real_, p = NA_real_))
  c(beta = coefficients["x", "Estimate"], p = coefficients["x", "Pr(>|z|)"])
}

con <- dbConnect(duckdb())
on.exit(dbDisconnect(con, shutdown = TRUE), add = TRUE)

all_rankings <- list()
all_order_tests <- list()
all_redundancy <- list()

for (input_index in seq_len(nrow(inputs))) {
  window_s <- inputs$window_s[[input_index]]
  path <- inputs$path[[input_index]]
  schema <- dbGetQuery(
    con,
    sprintf("DESCRIBE SELECT * FROM read_parquet('%s')", path)
  )
  feature_columns <- schema$column_name[
    grepl("__(base|shape|shuffle|reverse|coupling|quality)__", schema$column_name)
  ]
  metadata <- c("task", "dataset_id", "subject_id", "session_id", "y")
  selected <- c(metadata, feature_columns)
  quoted <- paste(sprintf('"%s"', selected), collapse = ", ")
  data <- dbGetQuery(
    con,
    sprintf("SELECT %s FROM read_parquet('%s')", quoted, path)
  )
  data$window_s <- window_s

  groups <- unique(data[c("task", "dataset_id")])
  for (group_index in seq_len(nrow(groups))) {
    task <- groups$task[[group_index]]
    dataset_id <- groups$dataset_id[[group_index]]
    subset <- data[data$task == task & data$dataset_id == dataset_id, , drop = FALSE]
    if (length(unique(subset$y)) < 2) next

    valid_features <- feature_columns[
      vapply(
        subset[feature_columns],
        function(x) sum(is.finite(x)) >= max(30, nrow(subset) * 0.5) &&
          length(unique(x[is.finite(x)])) > 2,
        logical(1)
      )
    ]
    if (length(valid_features) == 0) next

    aucs <- vapply(valid_features, function(name) auc_rank(subset$y, subset[[name]]), numeric(1))
    ranking <- data.frame(
      window_s = window_s,
      task = task,
      dataset_id = dataset_id,
      feature = valid_features,
      feature_group = vapply(valid_features, feature_group, character(1)),
      auc = aucs,
      oriented_auc = pmax(aucs, 1 - aucs),
      both_class_subjects = both_class_subjects(subset$y, subset$subject_id),
      stringsAsFactors = FALSE
    )

    top_for_glm <- head(
      ranking$feature[order(ranking$oriented_auc, decreasing = TRUE, na.last = NA)],
      40
    )
    ranking$subject_fixed_beta <- NA_real_
    ranking$subject_fixed_p <- NA_real_
    if (ranking$both_class_subjects[[1]] >= 3) {
      for (name in top_for_glm) {
        result <- safe_glm(subset$y, subset[[name]], subset$subject_id)
        position <- match(name, ranking$feature)
        ranking$subject_fixed_beta[[position]] <- result[["beta"]]
        ranking$subject_fixed_p[[position]] <- result[["p"]]
      }
    }
    ranking$subject_fixed_fdr <- ave(
      ranking$subject_fixed_p,
      ranking$window_s,
      ranking$task,
      ranking$dataset_id,
      FUN = function(x) p.adjust(x, method = "BH")
    )
    all_rankings[[length(all_rankings) + 1]] <- ranking

    shape_names <- valid_features[grepl("__shape__", valid_features, fixed = TRUE)]
    order_rows <- list()
    for (shape_name in shape_names) {
      shuffle_name <- sub("__shape__", "__shuffle__", shape_name, fixed = TRUE)
      if (!(shuffle_name %in% valid_features)) next
      shape_auc <- auc_rank(subset$y, subset[[shape_name]])
      shuffle_auc <- auc_rank(subset$y, subset[[shuffle_name]])
      order_rows[[length(order_rows) + 1]] <- data.frame(
        window_s = window_s,
        task = task,
        dataset_id = dataset_id,
        shape_feature = shape_name,
        shuffle_feature = shuffle_name,
        shape_oriented_auc = max(shape_auc, 1 - shape_auc),
        shuffle_oriented_auc = max(shuffle_auc, 1 - shuffle_auc),
        order_advantage = max(shape_auc, 1 - shape_auc) - max(shuffle_auc, 1 - shuffle_auc),
        stringsAsFactors = FALSE
      )
    }
    if (length(order_rows)) {
      all_order_tests[[length(all_order_tests) + 1]] <- do.call(rbind, order_rows)
    }

    shape_ranking <- ranking[ranking$feature_group == "shape", , drop = FALSE]
    top_shape <- head(
      shape_ranking$feature[
        order(shape_ranking$oriented_auc, decreasing = TRUE, na.last = NA)
      ],
      30
    )
    top_shape <- intersect(top_shape, names(subset))
    if (length(top_shape) >= 2) {
      correlation <- suppressWarnings(cor(subset[top_shape], use = "pairwise.complete.obs"))
      upper <- which(upper.tri(correlation), arr.ind = TRUE)
      redundant <- sum(abs(correlation[upper]) >= 0.95, na.rm = TRUE)
      all_redundancy[[length(all_redundancy) + 1]] <- data.frame(
        window_s = window_s,
        task = task,
        dataset_id = dataset_id,
        top_shape_features = length(top_shape),
        pairs_abs_correlation_ge_095 = redundant,
        stringsAsFactors = FALSE
      )
    }
  }
  message("R analyzed window_s=", window_s, " rows=", nrow(data), " features=", length(feature_columns))
}

rankings <- do.call(rbind, all_rankings)
order_tests <- do.call(rbind, all_order_tests)
redundancy <- do.call(rbind, all_redundancy)

write.csv(rankings, file.path(output_dir, "univariate_feature_ranking.csv"), row.names = FALSE)
write.csv(order_tests, file.path(output_dir, "shape_vs_shuffle.csv"), row.names = FALSE)
write.csv(redundancy, file.path(output_dir, "shape_redundancy.csv"), row.names = FALSE)

top <- do.call(
  rbind,
  lapply(
    split(rankings, interaction(rankings$window_s, rankings$task, rankings$dataset_id)),
    function(frame) head(frame[order(frame$oriented_auc, decreasing = TRUE), ], 10)
  )
)
write.csv(top, file.path(output_dir, "top_features_by_task.csv"), row.names = FALSE)

order_flat <- do.call(
  rbind,
  lapply(
    split(
      order_tests,
      interaction(
        order_tests$window_s,
        order_tests$task,
        order_tests$dataset_id,
        drop = TRUE
      )
    ),
    function(frame) data.frame(
      window_s = frame$window_s[[1]],
      task = frame$task[[1]],
      dataset_id = frame$dataset_id[[1]],
      median_order_advantage = median(frame$order_advantage, na.rm = TRUE),
      p90_order_advantage = as.numeric(
        quantile(frame$order_advantage, 0.90, na.rm = TRUE)
      ),
      fraction_order_advantage_gt_002 = mean(
        frame$order_advantage > 0.02,
        na.rm = TRUE
      )
    )
  )
)
write.csv(order_flat, file.path(output_dir, "shape_vs_shuffle_summary.csv"), row.names = FALSE)

significant <- rankings[
  is.finite(rankings$subject_fixed_fdr) & rankings$subject_fixed_fdr < 0.05,
]
significant_summary <- aggregate(
  feature ~ window_s + task + dataset_id + feature_group,
  significant,
  length
)
names(significant_summary)[names(significant_summary) == "feature"] <- "significant_features_fdr_005"
write.csv(
  significant_summary,
  file.path(output_dir, "subject_fixed_effect_summary.csv"),
  row.names = FALSE
)

report <- c(
  "# R Temporal Shape Exploration",
  "",
  paste0("Generated rows ranked: ", nrow(rankings)),
  paste0("Shape-vs-shuffle comparisons: ", nrow(order_tests)),
  paste0("Subject-fixed significant features (FDR < .05): ", nrow(significant)),
  "",
  "## Shape Order Advantage",
  "",
  "Positive value means true temporal order beats shuffled values for same feature calculator.",
  "",
  "```",
  capture.output(print(order_flat, row.names = FALSE)),
  "```",
  "",
  "## Subject-Fixed Significant Feature Counts",
  "",
  "```",
  capture.output(print(significant_summary, row.names = FALSE)),
  "```",
  "",
  "## Redundancy",
  "",
  "```",
  capture.output(print(redundancy, row.names = FALSE)),
  "```"
)
writeLines(report, file.path(output_dir, "R_TEMPORAL_SHAPE_REPORT.md"))
