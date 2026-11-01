# Controller research decisions

Historical rulings retained from the task ledger, in chronological order.
They document design and scope decisions; frozen methods and observed results
remain authoritative. No positive outcome is required.

# SDD ledger — plan: experiments/local_guards_ml_retrain/PLAN.md
Baseline81fb026. Approved user plan implemented in existing research worktree/PR7.
Old v3/v4/FinBot/main report protected by baseline.json; no writes there permitted.
Task1: running ml_retrain_dev_author, policy-only independent oracle/dev data.
Task2: queued features/train/CAL/predict; task3 closed author only after freeze.
Task4: evaluation/native benchmarks; task5 independent audit + appendix + PR update.
Ruling: use separate payment_v3/A/B models with3 classes; archive-only lack of
ALLOW retained, not patched with synthetic positives behind that arm's name.
Ruling: fit weights source50/50 and equal base groups, mean1 normalization avoids
LR C=1 shrinking all signals due sum(weights)=1.
Ruling: normalizer/schema cannot authenticate caller JSON or infer external
writer ABA/current claim generation; trusted producer boundary unchanged.
Pre-created Task2 and closed-author briefs; closed author not dispatched before
freeze. Archive label shape confirmed: independent requirements A01..B03,
payment baseline via A08. Existing v4 CAL no fully known safe A denominator.
Task1 preflight: removed unrequested operation substring/name criteria from
independent oracle before any fit; genuine native currency sources allowed,
missing current Invoice field is not a universal source ban. Author correcting.
Ruling: native benchmark may attest parent link from actual runner context in a
new experiment adapter for BOTH rules/ML; original legacy snapshot remains
separate. No old runtime edit or fabricated permission. Must disclose enrichment.
Task1 delivered/committed2f92cd8; read-only reviewer ml_retrain_data_review found
2 typed-envelope defects in valid_v3. Fix round1 author regressions failed then
28pass; all8000 complete gold/observation/metadata bytes unchanged. Committed
c8b2c54; scoped re-review pending at task-1-fix-1.diff. No fits/test generation yet.
Final duplicate-aware split908components,1500/500rawbase groups,6000/2000rows;
435 normalized cross-split signatures removed without changing cases/labels.
Task2 brief updated efficiency/weights/split semantics, not committed yet.
Task1: complete (2f92cd8..c8b2c54, review accepted both findings addressed; audit
preserved dev-review.md/dev-rereview.md). Task2 baseline is commit after accepted
audit/feature brief. Next implementer receives only feature-training brief.
Task2 active ml_retrain_features_engine, baselinec24ff91. Exact interfaces,
constraints and source allowlist in provenance/features-training-brief.md.
No full fits before implementation review. Evaluation/benchmark brief prepared
but not dispatched. Task3 closed author pending verified model-freeze.

Task2 reviewed8e805e0:2Important(FeatureBatch CAL wrapper loss;P2 mismatched delegation-call gate), no full fits. Fix round1 dispatched original implementer.
Prepared82245 TRAIN/CALrows immutable, archive55492/18753 +synthetic6000/2000.
Ruling: no-safe-CAL may be flagged algebraic feasibility but cannot establish measured <=5% FPR; reports must preserve null denominator. Actual shared CAL has synthetic safe states. Cost if wrong: misleading feasibility for unsupported contracts.
Task2 fix round1/5:2126729 fixes FeatureBatch +P2 linkage,17 own tests green; scoped reviewer active. Prepared corpus committed for reproduction.
Task2: complete(c24ff91..2126729, scoped review accepted both fixes46c117d). Full72fit running PTYsession5710; output frozen/, log fit.log. No closed author before verify_freeze succeeds.

Pre-freeze CAL audit found synthetic variants shareepisode although counterfactual/samecut, A/Bsafeepisodes0. Stopped fitPID76109(SIGINT,status130),66partial models moved to ignored scratch; hashes/reason saved aborted-calibration-unit-run.json. No closedtest exists. Task1 author correcting episode_id only, preserve group/split/obs/gold.
Ruling: independent synthetic state is its own episode; base/collision groups remain grouping units for splits/weights/CI. Prior shared episode grouped mutually exclusive variants as one execution. Cost if wrong: different calibration objective; explicit correction before test.
Task1 fix round2/5:26774d2 changes episode IDs only,31testsPASS, independent data re-reviewPASS. Obs/gold/oracle/groups/splits unchanged. Prepared rebuilt82245rows.
Task2 fix round2/5:5c62bf9 requires positive safe denominator,18testsPASS, scoped re-review active.
Ruling: supersede prior algebraic no-safe feasibility: zero safe CAL episodes is infeasible/unassessable, never a feasible5%FPR. Actual bug showed misleading feasibility could pass. Cost if wrong: abstention despite an analytically possible rule, preferable to unmeasured safety claim.
Task2 extra denominator fix accepted f0df963. Rebuilt82245inputs, full72fit restarted PTY86713 with OMP/OPENBLAS/VECLIB threads2, environmentreceipt persisted. No testauthor yet.
Ruling: cap local numerical runtime to2threads uniformly for accepted fits and all method/control benchmarks; fixed LR/CatBoost hyperparameters unchanged. Cost if wrong: timing differs from default host parallelism, environment disclosed.
Accepted full72fit PTY86713 finished exit0, no warnings. verify_freeze361artifacts72models passed; model-freeze.json SHA929793c35c692e6f2bd88a892784a6af374d447f69b62604d9fba32c46e06bfd. Closedauthor fresh ml_retrain_closed_author active afterfreeze. DO NOT OPEN closedgold/source/embargoedreport before predictions+receipt. Methods/PLAN/source immutable from now; no fixes after gold disclosure.
Upstream main e12a85e merges4modelreport21ffcf1; artifact/inputpayload identical924e64b already inventoried, no addedtraces. PR7stillMERGEABLE.

External delivery coordination: thread01a19769-dfae-7361-a83c-5313c389518b has user-approved v4.2 followup in separate worktree research/finbot-v4-followup, separateexperiment local_guards_v4_followup, no interference with ML. Verified direct userplan via read_thread before messaging. Agreed order: otheragent pushes separatebranch, waits; root completes ML/audit/push/readback PR7, then sends exactSHA+handoff to thatthread; otheragent may mergeMLintoitsworktree andFFupdatePR7 afterhandoff. Root DOESNOTmergev4.2 or change mainreport. Need send finalhandoff afterMLdelivery.
Task3 authorDONE1200states10families120pairedgroups1200episodes, sealedad77387; parent NOTreadgold/source/report/manifest. Fresh ml_retrain_closed_review active policy/label/overlap audit. Outputlabelblind handoff safe only.
Task4 phase1 implementation ml_retrain_evaluation active in parallel with read-onlytestaudit (one implementer). Briefprovenance/evaluation-benchmark-brief.md; goldembargoexplicit, no fullarchive/72benchmarks before codereview. Need labelblindcontrols CLI for parentprediction receipt before goldrelease. Task4basead77387.
Task4 phase1 safecheckpoint: evaluation.py+test_evaluation.py7testsPASS, native driverpending20-30min; writesPAUSED originalevalworker for serialized testauthorfix, read-onlynative analysisokay. ControlsCLIprovided: evaluation.py controls --observations closed/observations... --metadata closed/metadata... --output results/closed-controls, noTFIDFbydefault. Need codefix identified beforefullruns: checkpoint/familyslices must preserve globalfirstSTOP reachability.
Ruling: benchmarkcommonP2adapter may derive parent AND call_id from actual trusted _INVOKING parent/delegation invocation before proofconstruction, sameforrules/ML; absent linkage staysunknown. OldRuntime generated newcheckingcall, incompatiblewithfrozengate; disclose enrichment and keep oldsnapshotdiagnostic. Cost if wrong: benchmarkmodels a prospective producer instead of deployed native evidence, cannotclaimarchival/nativeprovenance alreadyexisted.
Task3 fixround1 accepted:8labelslots4states,2annotationremovals,0remaining;obs/IDs/groups/episodesunchanged. Revieweroutputsclosed-rereview.md/json. Task3complete authorad77387..5b2f8a3, accepted.
Task4evaluation.py stablecheckpoint3b9759;9ownfixturetests and13native smoketrials PASS reported (fullphase1reportpending), benchmark.py new. ParentoriginalMLpredict session68938 andcontrols63343 finishedexit0; independentlyverified all144methods exacteligibleprefixsets, controls3receipt. Sealedclosedpackage andpredictions committed1127d59 BEFOREgold. StillNOgold opened; waitingworkerphase1completion plusvalidationhardening thenexplicitgoldrelease. RootmustNOT forget toreleasegold and then runmeasurements afterphase1codereview.
Otherfollowupseparatebranchpushed6871daa0f21754540763cbd2fe400badf9d12402,agentwaitingourhandoff;DO NOTmergeitintoMLcheckout. AfterfinalPRpush/sendhandoffthread01a19769-dfae-7361-a83c-5313c389518b.
Task4phase1stableccc1e4f:14ownfixturetests,13native trials,72freeze+protectedhashes verified. Fresh evaluation-review active scopedphase1diff. GOLDRELEASE permitted now results/closed-gold-release.json AFTERpredictionscommit1127d59. Parent/evaluator mayreadlabels/reports now; NOmethod/feature/model/threshold changes. No fullruns untilphase1reviewaccepted.

Protocol audit ml_retrain_protocol_audit confirms highseveritysourcebinding defect: A04proofbindsdelegation_call_id, features+gate wronglycheckingcall and equality. CALlegitimatevsforeignproof alias exactfeatures; notMLlimit. Originalfrozenassessmentmuststand. NewseparateREVISION_2_PLAN.md pre-registersminimalcorrectedfeature/gate version, same data/params/thresholdsearch, reuse48onlyunderexactmatrixproof/refit24, freshindependent1200closed AFTERV2freeze. No oldsource/model/threshold/gold repair.
Ruling: implement separate correctedassessment rather than claiming invalidfeature/gate negatives reflectMLability. Needed foruserfaircomparison; costextra localfits/independenttest/time, no APIcalls. Original1200isopen diagnostic now.
Delivery order UPDATED with explicit coordination: otherthread01a19769 may FFpublish v4.2 PR7now; root NOparallelpush. RootMLlocal untouched, preserveoldmainreportthroughpurekaudit. AfterMLaudit premergeSHA, fetch/merge publishedPRhead, verify MLexperimenttree unchangedfromauditedSHA andmainreportexactlyfromotherauthorizedSHA, runmodelverify_freeze (notbaselineoldreporthash) andFFpushcombined. Baseline.jsonunchanged; oldreportidentity evidenceonpremergeMLSHA. OtheragentwillprovidePRreadback.
Task4V1executionworkerexistingCLIsONLY: native148methodsx5completed, singleactive,loadnext; sourcesnoedits. Revision2enginefreshnone active newfilesonly, testsCPUhelduntilquietbenchclear. Protocolsourceauditreportcommitted4b40245.
V1 timing all72commands complete exit0, CPUclear sentrevision2engine. Originalevalworker now prediction/scoring only, no sources; rawoutputs results/original-v1/. Revision2engine own12testsPASS, finalreport/readlogpending; newfiles features_revision2.py/models_revision2.py/experiment_revision2.py/test_revision2.py. Sourcefix+reusepipelinefeaturebinding explicit, no original edits.
OtherthreaddeliveryDONE: PR7 FFhead3bf981bed0a4175dbd3019fa7ebc49a8a0dc6e1a, OPEN/MERGEABLE; mainreportblob2ed4f9e1dc36b22afa7519bafdcbf2c91c99e877. RootMLstilllocal. AfterpureMLaudit,fetch/merge originPRbranch, assert MLtree fromauditedSHA unchangedandmainreportfrom3bf981, verifybothmodel freezes, thenFFpushappendix. No mainmerge.
Revision2enginecomplete and independentlyaccepted 3970e0c..2fc8668 +rereview. Fullfit PTY49432 exit0,72models434artifacts verifyPASS. model-freeze-revision2.json SHA c3289efda53ad12657db312dff8d7f694fad2dee14496613330c698e9067aba2. NOclosed_revision2 exists. Waiting metricwriterfinish before newauthor (oneimplementer).
Revision2measurement review found lateSTOPassert inherited; writerfixedbenchmark9testsPASS thensourceEregistrygap3373vs3378 discovered5zeroprefixepisodes. Newmeasurementwriter active optional--episodes +explicit--model-freeze +unassessed evidence/bounds; oldsource/resultsunchanged. Need scopedre-reviewcompletefix; newauthorcanstart oncewriterDONE because inferencefeatures/models/thresholds frozen already andscoring-only changes are notmethods.
Originalv1allmeasurements+allarchiveclosedCALold320/400 done, noactivecompute; execution-reportavailable, archivegapqualifiedpendingcorrectedrescoreusingnewCLI.
Ruling: methodfreeze remains valid while scoring-only population/STOP-accounting repair completes; no classifier/input contract/threshold change and newtest not authoredyet. Preserve separate sourceversion/provenance ofmeasurementcode. Cost if wrong: methodological ambiguity, make code/receipt chronology explicit.

Revision2 fresh independent1200 author/reviewer complete:13labelslots11states corrected before predictions; final observations890adbd5, metadata8fba84f1, golde9e90732. Shared486historywitnesses and460v3envelopes checked; source-read deviations/31bootstrapcomponents disclosed. Puretestcommit1792bbd3. Parentgoldstillblind.
OriginalV1 correctedaccounting complete:archive3378/CAL2727registry,5/2zero-prefix retainedunassessed, allprimaryreached/actionmetrics unchanged. InitialR2native743trials completed but CPUcontention; excludedprimarylatency, preservedpreliminary. Noactiveheavycompute.
Task4 executionpolicy repair: originalANDrevision2 batchpredict failedbeforegold on malformedtimestamp int<str in immutableapproval_relations. Partialfiles preserved results/closed2/failed-batch-before-error-wrapper. Solewriter ml_retrain_revision2_evaluation active new replay_predictions.py +newmeasurement Frozen.one catch; all frozenlearnedmethod files unchanged.
Ruling: generic per-check exception becomes UNKNOWN/STOP with unavailable probabilities, matching predeclared execution error policy; no coercion, schema filtering, case-specific patch or learned-method repair. Cost if wrong: adapter is extraexecutioncode, so valid-row parity and bothoriginal/revision2 gates require independent scopedreview beforeblindpredictions. Parentwillcommitcompletepredictionsbeforegoldrelease.

Quietnative/single/load completeexit0; CPUclear sentotherthread+analysiswriter. Native151methods743trials(37complete706STOPincluding3diagnostics),single147methods94080calls,load72freshworkers. ExecutionworkerSTARTED primaryNEW1200scoresbothversions completed219methodseach, thenCAL/open/archive; no furthertimingsplanned.
Postreleaseanalysisdiagnosis: paymentpairr2c0524/0525 onlyclearancesequence40vs25 aroundHOLD30, entireold38/new472featurevectorsidentical; policygoldALLOW/BLOCK andfrozenpaymentrulecorrect, LRnewmixedgatedALLOWboth. Genericnewproofrelationsencodebeforecut/perfactnewest butnotcrossfactHOLDclearanceorder; v3gatealsoomitsafterHOLD comparison. Analysisartifactpair-feature-diagnostic.json preservesfeatureonlyboundedcheck,nopred/refit. NotinherentMLlimit.
Ruling: preservebothfrozenassessmentsandreportthispost-testrepresentationalgap explicitly insteadofrepairingmethods/retrainingagainstnewlyrevealedtest. Userrequiresno methodfixaftergoldwithinassessment. Costifwrong: experimentdoesnotestablishcompleteinformationparity/generalrules-vsMLsuperiority; honestpartialrepresentationnegative isclaimedonlyasmeasuredimplementationresult, notintrinsicMLfailure. Anyfurthercorrectionrequiresnewversionandfreshvalidationoutsidecurrentfrozencomparison.

Finalscopedrereview7b92acb6 R1/R2ADDRESSED, specPASS/qualityPASS. ResidualP3exactphrase158outsideBOTHtrain+cal: Ruling: applyliteralwordingalreadyproposedandfact-verifiedbyreviewer withone-occurrencetablehashcheck/reporthashrefresh, withoutanotherreviewwave orcalculation — removesreaderambiguitywithoutnumeric/methodchange — costifwronglimitedtothisphrase;countsindependentlyverified.
Ruling: useralreadyexplicitlyrequestedexistingPRupdate, sofinishwiththatselectedintegrationoptionwithoutnewpermissionmenu; nomaintargetmerge — authorizationpersists — costifwrongonlyordinaryreviewablePRbranchupdate, protectedmainuntouchedbyours.
Ruling: officialper-worktreesparsecheckoutwill excludeonlyincominglocal_guards_v4_followupworkingcopieswhenmergingauthorizedotherPRhead, keepingfullGit/PRtreeandallMLfiles — avoids317560618Bduplicatecheckoutunderlowdisk — costifwrongthoseunrelatedfollowupfilesneedmaterializationlater;originalworktree/Gitbytesintact.
