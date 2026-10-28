where i am currently 

see first of all i explored the data undertood it which columns, what each columns means and im getting some feature engineering in my mind very quickly 

but before that we have alot to do 

first of all we decided to use two models
one will get triggered if the customer or user canceled its membership before N days of renewal but turned out the data that we have may not support it(assumption) adn it will turn out really bad and the business analogy is that we can use that later like if the customer canceled and then get ghosted even if we offer he will t take the discount. 

so we can use a feature that will get save before N days of renewal that will say, is subsicription canceled right now. 

and i also understood the missing values are not missng because they weren't capture, they were missing becasue of conditions and tells us a different thing that if value is naan it means 'this"

Now our main goal for tommorow is we have to first of all check that the feature in each datatable we currently have, do they will be available before N number of days of renewal
we also have to chekc a very important thing that is right now in the data, are these values got saved or are these values came before that 10 days of churning out and non churning because ultimately if these values came after N days of came after churning because first of all the model will not be usefull if it will predict that the person can churn or not right 1 or 2 days before the renewal because at that point alot of things can be happened may be they canceled their membership already and now they do not want to cancel it becasue changing persons mind is way more difficult at the moment he decided somehting and there are more chances that he ghosted the platform already so he will not be able to see the discount or offer. our main goal is that first of all capture the past pattens that is this person is gonna churn out or not?
now we will observe that before N days of renewal and also in that moment may be he canceled his membership and due to that he will have more chances to churn out and in that case we will try that he will put his card back and if he didn't canceled the membership yet but still have high chances of churning out then our goal is to give him the offer which after seeing that and saving that he will not take his card out. but there is a problem user can notice the pattern of it and if the churned user have high amount of canceled membership before N days so it will get more weight and users can notice that and do that deliberately to get the discount but we have to stop it from happening somehow by seeing where each feature can fail when we will do featuree engineering.

