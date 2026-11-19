import test from 'node:test';
import assert from 'node:assert/strict';
import {normalizeVacancy,rankVacancies} from '../partner-vacancies.js';
test('active status does not imply verification',()=>{
 const row={'ID':'42','Статус предложения':'Активная','Проект / заказчик':'Empik','Город / местоположение':'Sochaczew','Количество':'15','ЗАРАБОТНАЯ ПЛАТА':'28 zł netto'};
 const v=normalizeVacancy(row);
 assert.equal(v.source_active,true);
 assert.equal(v.slots,15);
 assert.equal(v.source_row,'42');
 assert.equal(v.pay_raw,'28 zł netto');
});
test('missing project or city is rejected',()=>{
 assert.equal(normalizeVacancy({'Проект / заказчик':'X'}),null);
});
test('matching ranks by city and housing without automatic eligibility decisions',()=>{
 const jobs=[{city:'Łódź',housing_raw:''},{city:'Sochaczew',housing_raw:'bezpłatne'}];
 const result=rankVacancies(jobs,{city:'Sochaczew',housing:true});
 assert.equal(result[0].city,'Sochaczew');
 assert.equal(result[0].match_score,5);
});
