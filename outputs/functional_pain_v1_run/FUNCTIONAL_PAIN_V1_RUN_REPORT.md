# Functional Pain V1 Learning Run

Rows: 10580

## Label Counts

```text
       sympathetic_activation  parasympathetic_recovery_proxy  homeostasis  activity_control
count               9590.0000                     5802.000000  8636.000000      10040.000000
mean                   0.4683                        0.176146     0.479968          0.098606
```

## Best Group-CV Metrics

```text
                        target                  model         feature_set    auc  average_precision  brier  feature_count
              activity_control               logistic        dataset_only 1.0000             1.0000 0.0000              2
              activity_control            extra_trees portable_base_shape 0.9949             0.9659 0.0234             86
              activity_control hist_gradient_boosting portable_base_shape 0.9945             0.9634 0.0156             86
              activity_control               logistic    aggressive_shape 0.9888             0.8595 0.0244            542
              activity_control               logistic portable_base_shape 0.9726             0.8503 0.0564             86
                   homeostasis               logistic portable_base_shape 0.6765             0.6482 0.2277             86
                   homeostasis            extra_trees portable_base_shape 0.6715             0.6561 0.2259             86
                   homeostasis               logistic        dataset_only 0.6707             0.6445 0.2070              2
                   homeostasis            extra_trees        quality_only 0.6680             0.6095 0.2277             27
                   homeostasis hist_gradient_boosting portable_base_shape 0.6584             0.6440 0.2432             86
parasympathetic_recovery_proxy               logistic    aggressive_shape 0.8281             0.4130 0.1662            542
parasympathetic_recovery_proxy               logistic portable_base_shape 0.7785             0.3545 0.1978             86
parasympathetic_recovery_proxy            extra_trees portable_base_shape 0.7651             0.3210 0.1534             86
parasympathetic_recovery_proxy hist_gradient_boosting portable_base_shape 0.7569             0.3373 0.1470             86
parasympathetic_recovery_proxy               logistic        dataset_only 0.7087             0.2863 0.2202              2
        sympathetic_activation            extra_trees        quality_only 0.7004             0.6328 0.2191             27
        sympathetic_activation               logistic        dataset_only 0.6929             0.6797 0.2067              2
        sympathetic_activation               logistic    aggressive_shape 0.6799             0.6296 0.2375            542
        sympathetic_activation               logistic        quality_only 0.6717             0.6054 0.2253             27
        sympathetic_activation hist_gradient_boosting portable_base_shape 0.6705             0.6340 0.2356             86
```

## Leave-Dataset Holdout

```text
                        target                              split                  model         feature_set    auc  average_precision  brier
        sympathetic_activation            leave_dataset_out:catsa               logistic portable_base_shape 0.4674             0.4869 0.2759
        sympathetic_activation        leave_dataset_out:painmonit               logistic portable_base_shape 0.3803             0.6476 0.3426
        sympathetic_activation   leave_dataset_out:painmonit_pmed               logistic portable_base_shape 0.4647             0.2062 0.4825
        sympathetic_activation leave_dataset_out:physiopain_watch               logistic portable_base_shape 0.5632             0.5317 0.3156
        sympathetic_activation       leave_dataset_out:rheumapain               logistic portable_base_shape 0.5005             0.0861 0.2179
        sympathetic_activation      leave_dataset_out:silver_pain               logistic portable_base_shape 0.5035             0.5224 0.2928
        sympathetic_activation            leave_dataset_out:wesad               logistic portable_base_shape 0.5559             0.5450 0.2811
        sympathetic_activation            leave_dataset_out:catsa hist_gradient_boosting portable_base_shape 0.4166             0.4559 0.2824
        sympathetic_activation        leave_dataset_out:painmonit hist_gradient_boosting portable_base_shape 0.4360             0.6770 0.3721
        sympathetic_activation   leave_dataset_out:painmonit_pmed hist_gradient_boosting portable_base_shape 0.5077             0.2065 0.3825
        sympathetic_activation leave_dataset_out:physiopain_watch hist_gradient_boosting portable_base_shape 0.5995             0.5959 0.3242
        sympathetic_activation       leave_dataset_out:rheumapain hist_gradient_boosting portable_base_shape 0.5985             0.1121 0.1881
        sympathetic_activation      leave_dataset_out:silver_pain hist_gradient_boosting portable_base_shape 0.3964             0.4776 0.3236
        sympathetic_activation            leave_dataset_out:wesad hist_gradient_boosting portable_base_shape 0.4802             0.4787 0.3697
        sympathetic_activation            leave_dataset_out:catsa            extra_trees portable_base_shape 0.4566             0.4612 0.2759
        sympathetic_activation        leave_dataset_out:painmonit            extra_trees portable_base_shape 0.3937             0.6605 0.3706
        sympathetic_activation   leave_dataset_out:painmonit_pmed            extra_trees portable_base_shape 0.4288             0.1681 0.3973
        sympathetic_activation leave_dataset_out:physiopain_watch            extra_trees portable_base_shape 0.5576             0.5458 0.2701
        sympathetic_activation       leave_dataset_out:rheumapain            extra_trees portable_base_shape 0.5897             0.1075 0.2127
        sympathetic_activation      leave_dataset_out:silver_pain            extra_trees portable_base_shape 0.4261             0.4836 0.2879
        sympathetic_activation            leave_dataset_out:wesad            extra_trees portable_base_shape 0.6164             0.5737 0.2693
        sympathetic_activation            leave_dataset_out:catsa               logistic        quality_only 0.4914             0.5303 0.3291
        sympathetic_activation        leave_dataset_out:painmonit               logistic        quality_only 0.4771             0.6983 0.3154
        sympathetic_activation   leave_dataset_out:painmonit_pmed               logistic        quality_only 0.6628             0.3011 0.5639
        sympathetic_activation leave_dataset_out:physiopain_watch               logistic        quality_only 0.5000             0.4750 0.3564
        sympathetic_activation       leave_dataset_out:rheumapain               logistic        quality_only 0.4831             0.0904 0.2308
        sympathetic_activation      leave_dataset_out:silver_pain               logistic        quality_only 0.4469             0.5146 0.2832
        sympathetic_activation            leave_dataset_out:wesad               logistic        quality_only 0.4591             0.4680 0.4942
        sympathetic_activation            leave_dataset_out:catsa            extra_trees        quality_only 0.5436             0.5384 0.2787
        sympathetic_activation        leave_dataset_out:painmonit            extra_trees        quality_only 0.5137             0.7131 0.4583
        sympathetic_activation   leave_dataset_out:painmonit_pmed            extra_trees        quality_only 0.4311             0.1681 0.2933
        sympathetic_activation leave_dataset_out:physiopain_watch            extra_trees        quality_only 0.5000             0.4750 0.3594
        sympathetic_activation       leave_dataset_out:rheumapain            extra_trees        quality_only 0.5010             0.0927 0.2300
        sympathetic_activation      leave_dataset_out:silver_pain            extra_trees        quality_only 0.4807             0.5329 0.2498
        sympathetic_activation            leave_dataset_out:wesad            extra_trees        quality_only 0.5609             0.5367 0.4901
        sympathetic_activation            leave_dataset_out:catsa               logistic        dataset_only 0.5028             0.5042 0.2583
        sympathetic_activation        leave_dataset_out:painmonit               logistic        dataset_only 0.5229             0.7196 0.2234
        sympathetic_activation   leave_dataset_out:painmonit_pmed               logistic        dataset_only 0.5007             0.2033 0.3169
        sympathetic_activation leave_dataset_out:physiopain_watch               logistic        dataset_only 0.5000             0.4750 0.2621
        sympathetic_activation       leave_dataset_out:rheumapain               logistic        dataset_only 0.5145             0.0963 0.3574
        sympathetic_activation      leave_dataset_out:silver_pain               logistic        dataset_only 0.5338             0.5581 0.2502
        sympathetic_activation            leave_dataset_out:wesad               logistic        dataset_only 0.5021             0.5041 0.2573
parasympathetic_recovery_proxy            leave_dataset_out:catsa               logistic portable_base_shape 0.6687             0.5440 0.2322
parasympathetic_recovery_proxy        leave_dataset_out:painmonit               logistic portable_base_shape 0.6145             0.0938 0.1791
parasympathetic_recovery_proxy leave_dataset_out:physiopain_watch               logistic portable_base_shape 0.6691             0.4191 0.3998
parasympathetic_recovery_proxy       leave_dataset_out:rheumapain               logistic portable_base_shape 0.8655             0.4927 0.1199
parasympathetic_recovery_proxy      leave_dataset_out:silver_pain               logistic portable_base_shape 0.6234             0.2161 0.1481
parasympathetic_recovery_proxy            leave_dataset_out:wesad               logistic portable_base_shape 0.6691             0.2482 0.1600
parasympathetic_recovery_proxy            leave_dataset_out:catsa hist_gradient_boosting portable_base_shape 0.5666             0.4741 0.2595
parasympathetic_recovery_proxy        leave_dataset_out:painmonit hist_gradient_boosting portable_base_shape 0.7121             0.1221 0.0701
parasympathetic_recovery_proxy leave_dataset_out:physiopain_watch hist_gradient_boosting portable_base_shape 0.6551             0.4146 0.2721
parasympathetic_recovery_proxy       leave_dataset_out:rheumapain hist_gradient_boosting portable_base_shape 0.9133             0.5780 0.1017
parasympathetic_recovery_proxy      leave_dataset_out:silver_pain hist_gradient_boosting portable_base_shape 0.6244             0.2083 0.1777
parasympathetic_recovery_proxy            leave_dataset_out:wesad hist_gradient_boosting portable_base_shape 0.6576             0.2528 0.1234
parasympathetic_recovery_proxy            leave_dataset_out:catsa            extra_trees portable_base_shape 0.5374             0.3848 0.2349
parasympathetic_recovery_proxy        leave_dataset_out:painmonit            extra_trees portable_base_shape 0.7046             0.1250 0.0790
parasympathetic_recovery_proxy leave_dataset_out:physiopain_watch            extra_trees portable_base_shape 0.6146             0.3871 0.2377
parasympathetic_recovery_proxy       leave_dataset_out:rheumapain            extra_trees portable_base_shape 0.9025             0.5202 0.1012
parasympathetic_recovery_proxy      leave_dataset_out:silver_pain            extra_trees portable_base_shape 0.6589             0.2076 0.1469
parasympathetic_recovery_proxy            leave_dataset_out:wesad            extra_trees portable_base_shape 0.6923             0.3116 0.1123
parasympathetic_recovery_proxy            leave_dataset_out:catsa               logistic        quality_only 0.6568             0.4846 0.2469
parasympathetic_recovery_proxy        leave_dataset_out:painmonit               logistic        quality_only 0.4656             0.0637 0.8390
parasympathetic_recovery_proxy leave_dataset_out:physiopain_watch               logistic        quality_only 0.5334             0.3327 0.2344
parasympathetic_recovery_proxy       leave_dataset_out:rheumapain               logistic        quality_only 0.3634             0.1425 0.3100
parasympathetic_recovery_proxy      leave_dataset_out:silver_pain               logistic        quality_only 0.4714             0.1446 0.5310
parasympathetic_recovery_proxy            leave_dataset_out:wesad               logistic        quality_only 0.5451             0.1636 0.1383
parasympathetic_recovery_proxy            leave_dataset_out:catsa            extra_trees        quality_only 0.5197             0.4110 0.2393
parasympathetic_recovery_proxy        leave_dataset_out:painmonit            extra_trees        quality_only 0.5344             0.0743 0.1695
parasympathetic_recovery_proxy leave_dataset_out:physiopain_watch            extra_trees        quality_only 0.5334             0.3327 0.2377
parasympathetic_recovery_proxy       leave_dataset_out:rheumapain            extra_trees        quality_only 0.5947             0.2905 0.3417
parasympathetic_recovery_proxy      leave_dataset_out:silver_pain            extra_trees        quality_only 0.4639             0.1450 0.3999
parasympathetic_recovery_proxy            leave_dataset_out:wesad            extra_trees        quality_only 0.5425             0.1569 0.1372
parasympathetic_recovery_proxy            leave_dataset_out:catsa               logistic        dataset_only 0.5149             0.3732 0.2396
parasympathetic_recovery_proxy        leave_dataset_out:painmonit               logistic        dataset_only 0.5344             0.0743 0.1068
parasympathetic_recovery_proxy leave_dataset_out:physiopain_watch               logistic        dataset_only 0.5334             0.3327 0.2169
parasympathetic_recovery_proxy       leave_dataset_out:rheumapain               logistic        dataset_only 0.5798             0.2140 0.1541
parasympathetic_recovery_proxy      leave_dataset_out:silver_pain               logistic        dataset_only 0.4893             0.1526 0.1444
parasympathetic_recovery_proxy            leave_dataset_out:wesad               logistic        dataset_only 0.5333             0.1486 0.1363
                   homeostasis            leave_dataset_out:catsa               logistic portable_base_shape 0.5570             0.5740 0.2553
                   homeostasis        leave_dataset_out:painmonit               logistic portable_base_shape 0.6192             0.3764 0.2283
                   homeostasis leave_dataset_out:physiopain_watch               logistic portable_base_shape 0.5741             0.5771 0.3020
                   homeostasis       leave_dataset_out:rheumapain               logistic portable_base_shape 0.4939             0.9226 0.1888
                   homeostasis      leave_dataset_out:silver_pain               logistic portable_base_shape 0.5111             0.5099 0.3153
                   homeostasis            leave_dataset_out:wesad               logistic portable_base_shape 0.5895             0.5757 0.3325
                   homeostasis            leave_dataset_out:catsa hist_gradient_boosting portable_base_shape 0.4442             0.4650 0.2942
                   homeostasis        leave_dataset_out:painmonit hist_gradient_boosting portable_base_shape 0.4495             0.2588 0.2204
                   homeostasis leave_dataset_out:physiopain_watch hist_gradient_boosting portable_base_shape 0.5938             0.6094 0.3394
                   homeostasis       leave_dataset_out:rheumapain hist_gradient_boosting portable_base_shape 0.5826             0.9314 0.1921
                   homeostasis      leave_dataset_out:silver_pain hist_gradient_boosting portable_base_shape 0.3424             0.3711 0.3187
                   homeostasis            leave_dataset_out:wesad hist_gradient_boosting portable_base_shape 0.5765             0.5575 0.4235
                   homeostasis            leave_dataset_out:catsa            extra_trees portable_base_shape 0.5116             0.5241 0.2553
                   homeostasis        leave_dataset_out:painmonit            extra_trees portable_base_shape 0.4918             0.2900 0.2137
                   homeostasis leave_dataset_out:physiopain_watch            extra_trees portable_base_shape 0.5502             0.5971 0.2698
                   homeostasis       leave_dataset_out:rheumapain            extra_trees portable_base_shape 0.5587             0.9256 0.1972
                   homeostasis      leave_dataset_out:silver_pain            extra_trees portable_base_shape 0.3648             0.3789 0.2766
                   homeostasis            leave_dataset_out:wesad            extra_trees portable_base_shape 0.6288             0.6466 0.2770
                   homeostasis            leave_dataset_out:catsa               logistic        quality_only 0.4919             0.4897 0.3218
                   homeostasis        leave_dataset_out:painmonit               logistic        quality_only 0.4771             0.2812 0.3457
                   homeostasis leave_dataset_out:physiopain_watch               logistic        quality_only 0.5000             0.5250 0.3754
                   homeostasis       leave_dataset_out:rheumapain               logistic        quality_only 0.4831             0.9021 0.1857
                   homeostasis      leave_dataset_out:silver_pain               logistic        quality_only 0.4896             0.4680 0.2741
                   homeostasis            leave_dataset_out:wesad               logistic        quality_only 0.5283             0.5280 0.4960
                   homeostasis            leave_dataset_out:catsa            extra_trees        quality_only 0.5588             0.5459 0.2527
                   homeostasis        leave_dataset_out:painmonit            extra_trees        quality_only 0.4771             0.2812 0.3418
                   homeostasis leave_dataset_out:physiopain_watch            extra_trees        quality_only 0.5000             0.5250 0.3810
                   homeostasis       leave_dataset_out:rheumapain            extra_trees        quality_only 0.5026             0.9080 0.1862
                   homeostasis      leave_dataset_out:silver_pain            extra_trees        quality_only 0.5159             0.4821 0.2509
                   homeostasis            leave_dataset_out:wesad            extra_trees        quality_only 0.5720             0.5474 0.4828
                   homeostasis            leave_dataset_out:catsa               logistic        dataset_only 0.5028             0.4990 0.2920
                   homeostasis        leave_dataset_out:painmonit               logistic        dataset_only 0.5229             0.3023 0.2064
                   homeostasis leave_dataset_out:physiopain_watch               logistic        dataset_only 0.5000             0.5250 0.3044
                   homeostasis       leave_dataset_out:rheumapain               logistic        dataset_only 0.5145             0.9093 0.4956
                   homeostasis      leave_dataset_out:silver_pain               logistic        dataset_only 0.5338             0.4810 0.2764
                   homeostasis            leave_dataset_out:wesad               logistic        dataset_only 0.5021             0.4983 0.2924
```

## Export Status

```yaml
portable_json: functional_pain_v1_portable_logistic.json
sklearn_joblib: written locally but ignored by git
onnx: not exported; skl2onnx not installed in this environment
coreml: not exported; coremltools not installed in this environment
portable_loss: none for logistic JSON if runtime implements median impute + standard scale + sigmoid exactly
```

## Interpretation

This run trains weak state proxies, not clinical pain truth. Sympathetic and
homeostasis labels have external task support. Parasympathetic recovery is the
weakest target because current datasets rarely label active recovery or vagal
state directly; it is bootstrapped from high-IBI, low-HR, low-EDA, low-motion
windows.

Feature/control divergence matters:

- if `dataset_only` approaches main model AUC, protocol shortcut risk remains.
- if `quality_only` performs well, sensor availability is leaking state.
- if leave-dataset-out collapses, model is not portable yet.

Final export payload targets: ['sympathetic_activation', 'parasympathetic_recovery_proxy', 'homeostasis']
