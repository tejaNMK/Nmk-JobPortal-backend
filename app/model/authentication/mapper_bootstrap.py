def bootstrap_mappers() -> None:
    """Import the full model graph in dependency order."""

    # ── Authentication models ────────────────────────────────────────────────
    
    from app.model.authentication.user_role import UsersRole              
    from app.model.authentication.password_history import PasswordHistory  
    from app.model.authentication.password_reset_token import PasswordResetToken  
    from app.model.authentication.person import Person                    
    from app.model.authentication.email_verification_token import EmailVerificationToken  
    from app.model.authentication.mobile_verification import MobileVerification 
    from app.model.authentication.user_session import UserSession          
    from app.model.authentication.role import Role                       

    # ── Master / lookup data (dropdowns) ─────────────────────────────────────
    from app.model.master_data.country import MasterCountry
    from app.model.master_data.location import MasterLocation
    from app.model.master_data.notice_period import MasterNoticePeriod
    from app.model.master_data.salary_expectation import MasterSalaryExpectation
    from app.model.master_data.target_role import MasterTargetRole
    from app.model.master_data.candidate_target_role import CandidateTargetRole
    from app.model.master_data.job_category import MasterJobCategory

    # ── Candidate-side models ────────────────────────────────────────────────
   
    from app.model.candidate_model.candidate_resume_detail import CandidateResumeDetail 
    from app.model.candidate_model.candidate_resume import CandidateResume               
    from app.model.candidate_model.candidate_saved_search import CandidateSavedSearch  
    from app.model.candidate_model.job_alert import JobAlert                            
    from app.model.candidate_model.job_alert_notification_delivery import JobAlertNotificationDelivery
    from app.model.candidate_model.search_keyword import SearchKeyword                 
    from app.model.candidate_model.candidate_saved_job import CandidateSavedJob   
    from app.model.employer_model.job_skill import JobSkill                
    from app.model.employer_model.job_posting_audit import JobPostingAudit 
    from app.model.employer_model.job import Job                           
    from app.model.candidate_model.job_recommendation import JobRecommendation      
    from app.model.candidate_model.job_application import JobApplication            
    from app.model.candidate_model.application_status_history import ApplicationStatusHistory  
    from app.model.candidate_model.application_note import ApplicationNote        
    from app.model.candidate_model.message_thread import MessageThread     
    from app.model.candidate_model.message import Message                  
    from app.model.candidate_model.profile_view_event import ProfileViewEvent          
    from app.model.candidate_model.candidate_company_following import CandidateCompanyFollowing  
    from app.model.candidate_model.candidate_profile import CandidateProfile  

    # ── Employer-side models ─────────────────────────────────────────────────
    from app.model.employer_model.employer_profile import EmployerProfile              
    from app.model.employer_model.company_profile import CompanyProfile                
    from app.model.employer_model.ai_job_description_usage import AIJobDescriptionUsage
    from app.model.employer_model.ai_candidate_match import AICandidateMatch
    from app.model.employer_model.candidate_ai_insight import CandidateAIInsight
    from app.model.employer_model.job_metrics import JobMetrics                        
    from app.model.employer_model.shortlisted_candidate import ShortlistedCandidate    
    from app.model.employer_model.candidate_recommendation import CandidateRecommendation 
    from app.model.employer_model.interview import Interview                          
    from app.model.employer_model.interviewer import Interviewer
    from app.model.employer_model.interview_interviewer import InterviewInterviewer                          
    from app.model.employer_model.interview_history import InterviewHistory                          
    from app.model.authentication.users import Users                      
    from app.model.contact_us_model import ContactUsInquiry        
    from app.model.employer_model.candidate_invitation import CandidateInvitation    


    from app.model.notification import Notification
    from app.model.subscription.subscription import Subscription
    from app.model.subscription.user_subscription import UserSubscription
    from app.model.subscription.subscription_history import SubscriptionHistory
    from app.model.subscription.subscription_usage import SubscriptionUsage
    from app.model.activity_log import ActivityLog
    from app.model.system_settings import SystemSettings
